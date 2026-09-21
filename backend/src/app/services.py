from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .errors import ConflictError, GenerationUnavailableError, NotFoundError, ValidationError
from .generation import OpenAIRecipeGenerator, build_generation_context
from .optimizer import WasteFirstOptimizer
from .repositories import (
    IngredientRepository,
    MealPlanRepository,
    MealPlanPreviewRepository,
    PantryRepository,
    ProfileRepository,
    ReceiptRepository,
    RecipeRepository,
    ShoppingListRepository,
    WasteRepository,
)
from .schemas import (
    MealPlanCreate,
    MealPlanPatch,
    MealSlotPatch,
    GeneratedRecipeCandidate,
    PlanGenerationRequest,
    PlanReoptimizeRequest,
    PantryItemCreate,
    PantryItemPatch,
    OnboardingPut,
    ProfilePatch,
    ReceiptCreate,
    ReceiptExtraction,
    ReceiptPatch,
    RecipeCreate,
    RecipePatch,
    ShoppingListItemPatch,
    WasteEventCreate,
)


def _database_message(exc: DBAPIError) -> str:
    message = str(getattr(exc, "orig", exc)).splitlines()[0]
    return message.removeprefix("<class 'asyncpg.exceptions.RaiseError'>: ")


def _translate_workflow_error(exc: DBAPIError) -> None:
    message = _database_message(exc)
    conflict_markers = ("not found", "must be", "needs", "exceeds", "required")
    if any(marker in message.lower() for marker in conflict_markers):
        raise ConflictError(message) from exc
    raise ValidationError("Database workflow rejected the request") from exc


class ProfileService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = ProfileRepository(session, user_id)

    async def get(self):
        return await self.repo.get()

    async def update(self, payload: ProfilePatch):
        return await self.repo.update(payload.model_dump(exclude_unset=True, mode="json"))

    async def complete_onboarding(self, payload: OnboardingPut):
        return await self.repo.complete_onboarding(payload.model_dump(mode="json"))


class IngredientService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = IngredientRepository(session, user_id)

    async def list(self, **kwargs):
        return await self.repo.list(**kwargs)

    async def package_options(self):
        return await self.repo.package_options()

    async def storage_rules(self):
        return await self.repo.storage_rules()


class PantryService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = PantryRepository(session, user_id)
        self.ingredients = IngredientRepository(session, user_id)

    async def list(self, **kwargs):
        return await self.repo.list(**kwargs)

    async def expiring(self, days: int, limit: int, offset: int):
        return await self.repo.list(
            status="available",
            best_before_lte=date.today() + timedelta(days=days),
            limit=limit,
            offset=offset,
        )

    async def get(self, item_id: int):
        return await self.repo.get(item_id)

    async def create(self, payload: PantryItemCreate):
        await self.ingredients.require(payload.ingredient_id)
        values = payload.model_dump(exclude_none=True)
        values["remaining_quantity"] = (
            payload.remaining_quantity
            if payload.remaining_quantity is not None
            else payload.initial_quantity
        )
        if values["remaining_quantity"] == 0:
            values["status"] = "depleted"
        return await self.repo.create(values)

    async def update(self, item_id: int, payload: PantryItemPatch):
        current = await self.repo.get(item_id)
        values = payload.model_dump(exclude_unset=True)
        if "storage_state" in values and values["storage_state"] != current.storage_state:
            values["storage_state_changed_at"] = datetime.now(UTC)
        if "remaining_quantity" in values and values["remaining_quantity"] > current.initial_quantity:
            raise ValidationError("remaining_quantity cannot exceed initial_quantity")
        if values.get("remaining_quantity") == 0 and "status" not in values:
            values["status"] = "depleted"
        return await self.repo.update(item_id, values)

    async def delete(self, item_id: int) -> None:
        await self.repo.delete(item_id)


class RecipeService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = RecipeRepository(session, user_id)

    async def list(self, *, limit: int, offset: int):
        return await self.repo.list(limit=limit, offset=offset)

    async def get(self, recipe_id: int):
        return await self.repo.get(recipe_id)

    async def create(self, payload: RecipeCreate):
        values = payload.model_dump(exclude={"ingredients"})
        ingredients = [item.model_dump() for item in payload.ingredients]
        return await self.repo.create(values, ingredients)

    async def update(self, recipe_id: int, payload: RecipePatch):
        values = payload.model_dump(exclude_unset=True, exclude={"ingredients"})
        ingredients = None
        if "ingredients" in payload.model_fields_set:
            ingredients = [item.model_dump() for item in (payload.ingredients or [])]
        return await self.repo.update(recipe_id, values, ingredients)

    async def delete(self, recipe_id: int) -> None:
        await self.repo.delete(recipe_id)


class MealPlanService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.repo = MealPlanRepository(session, user_id)
        self.shopping_lists = ShoppingListRepository(session, user_id)

    async def list(self, *, limit: int, offset: int):
        return await self.repo.list(limit=limit, offset=offset)

    async def get(self, plan_id: int):
        return await self.repo.get(plan_id)

    async def create(self, payload: MealPlanCreate):
        values = payload.model_dump()
        selected = [meal_type.value for meal_type in payload.selected_meal_types]
        values["selected_meal_types"] = selected
        meals: list[dict[str, Any]] = []
        current = payload.start_date
        while current <= payload.end_date:
            meals.extend(
                {"meal_date": current, "meal_type": meal_type, "servings": 1, "status": "requested"}
                for meal_type in selected
            )
            current += timedelta(days=1)
        return await self.repo.create(values, meals)

    async def update(self, plan_id: int, payload: MealPlanPatch):
        return await self.repo.update(plan_id, payload.model_dump(exclude_unset=True))

    async def update_meal(self, plan_id: int, meal_id: int, payload: MealSlotPatch):
        values = payload.model_dump(exclude_unset=True)
        if values.get("recipe_id") is not None and "status" not in values:
            values["status"] = "generated"
        return await self.repo.update_meal(plan_id, meal_id, values)

    async def delete(self, plan_id: int) -> None:
        await self.repo.delete(plan_id)

    async def rebuild_shopping_list(self, plan_id: int):
        try:
            list_id = await self.session.scalar(
                text("select public.rebuild_shopping_list(:plan_id)"), {"plan_id": plan_id}
            )
            await self.session.flush()
        except DBAPIError as exc:
            _translate_workflow_error(exc)
        return await self.shopping_lists.get(int(list_id))


class MealPlanPreviewService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        generator: Any | None = None,
        optimizer: WasteFirstOptimizer | None = None,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = get_settings()
        self.previews = MealPlanPreviewRepository(session, user_id)
        self.profiles = ProfileRepository(session, user_id)
        self.ingredients = IngredientRepository(session, user_id)
        self.pantry = PantryRepository(session, user_id)
        self.recipes = RecipeRepository(session, user_id)
        self.plans = MealPlanRepository(session, user_id)
        self.shopping_lists = ShoppingListRepository(session, user_id)
        self.optimizer = optimizer or WasteFirstOptimizer()
        if generator is not None:
            self.generator = generator
        elif self.settings.openai_api_key:
            self.generator = OpenAIRecipeGenerator(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model,
                timeout_seconds=self.settings.openai_timeout_seconds,
            )
        else:
            self.generator = None

    @staticmethod
    def _meal_slots(request: PlanGenerationRequest) -> list[dict[str, Any]]:
        days = 1 if request.horizon == "today" else 7
        return [
            {
                "slot_key": f"{request.start_date + timedelta(days=offset)}:{meal_type}",
                "meal_date": request.start_date + timedelta(days=offset),
                "meal_type": str(meal_type),
            }
            for offset in range(days)
            for meal_type in request.meal_types
        ]

    async def _planning_inputs(self, request: PlanGenerationRequest):
        profile = await self.profiles.get()
        ingredients = await self.ingredients.all()
        package_options = await self.ingredients.package_options()
        storage_rules = await self.ingredients.storage_rules()
        pantry_items, _ = await self.pantry.list(
            status="available", best_before_lte=None, limit=10_000, offset=0
        )

        # Reuse the latest confirmed receipt unit price where the curated package lacks a price.
        price_history = await self.ingredients.receipt_unit_prices()
        priced_options = []
        for option in package_options:
            values = {
                "id": option.id,
                "ingredient_id": option.ingredient_id,
                "label": option.label,
                "quantity": option.quantity,
                "unit": option.unit,
                "estimated_price": option.estimated_price,
                "currency_code": option.currency_code,
                "is_default": option.is_default,
                "can_freeze": option.can_freeze,
                "price_source": "catalog" if option.estimated_price is not None else "unknown",
            }
            history = price_history.get(option.ingredient_id)
            if values["estimated_price"] is None and history and history[1] == request.currency_code:
                values["estimated_price"] = Decimal(str(history[0])) * Decimal(str(option.quantity))
                values["currency_code"] = history[1]
                values["price_source"] = "receipt_history"
            priced_options.append(SimpleNamespace(**values))
        return profile, ingredients, priced_options, storage_rules, pantry_items

    async def create(self, request: PlanGenerationRequest):
        if self.generator is None:
            raise GenerationUnavailableError(
                "OPENAI_API_KEY is not configured on the backend."
            )
        await self.previews.delete_expired()
        slots = self._meal_slots(request)
        profile, ingredients, package_options, storage_rules, pantry_items = (
            await self._planning_inputs(request)
        )

        generated: list[GeneratedRecipeCandidate] = []
        if request.horizon == "today":
            # Six candidates per requested meal type gives each slot useful swap depth.
            for meal_type in request.meal_types:
                scoped_slots = [slot for slot in slots if slot["meal_type"] == str(meal_type)]
                context = build_generation_context(
                    profile=profile,
                    request=request,
                    meal_slots=scoped_slots,
                    pantry_items=pantry_items,
                    ingredients=ingredients,
                    package_options=package_options,
                    storage_rules=storage_rules,
                    candidate_count=6,
                )
                recipes = await self.generator.generate(
                    context=context,
                    request=request,
                    profile=profile,
                    ingredients=ingredients,
                    required_meal_types={meal_type},
                )
                generated.extend(
                    recipe.model_copy(update={"candidate_id": f"{meal_type}-{recipe.candidate_id}"})
                    for recipe in recipes
                )
        else:
            count = min(
                self.settings.openai_candidate_limit,
                max(12, len(slots) + len(request.meal_types) * 3),
            )
            context = build_generation_context(
                profile=profile,
                request=request,
                meal_slots=slots,
                pantry_items=pantry_items,
                ingredients=ingredients,
                package_options=package_options,
                storage_rules=storage_rules,
                candidate_count=count,
            )
            generated = await self.generator.generate(
                context=context,
                request=request,
                profile=profile,
                ingredients=ingredients,
                required_meal_types=set(request.meal_types),
            )

        solution = self.optimizer.solve(
            request=request,
            profile=profile,
            meal_slots=slots,
            candidates=generated,
            ingredients=ingredients,
            pantry_items=pantry_items,
            package_options=package_options,
            storage_rules=storage_rules,
        )
        return await self.previews.create(
            {
                "status": "ready",
                "request": request.model_dump(mode="json"),
                "candidates": [item.model_dump(mode="json") for item in generated],
                "solution": solution,
                "prompt_version": self.settings.recipe_prompt_version,
                "model": self.settings.openai_model,
                "expires_at": datetime.now(UTC) + timedelta(hours=24),
            }
        )

    @staticmethod
    def _ensure_active(preview) -> None:
        expires_at = preview.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise NotFoundError("Meal-plan preview has expired")
        if preview.status == "failed":
            raise ConflictError(preview.failure_reason or "Meal-plan preview failed")

    async def get(self, preview_id: UUID):
        preview = await self.previews.get(preview_id)
        self._ensure_active(preview)
        return preview

    async def reoptimize(self, preview_id: UUID, payload: PlanReoptimizeRequest):
        preview = await self.previews.get(preview_id)
        self._ensure_active(preview)
        if preview.status == "confirmed":
            raise ConflictError("Confirmed previews cannot be changed")
        request_data = dict(preview.request)
        if payload.package_overrides:
            current = {
                item["ingredient_id"]: item for item in request_data.get("package_overrides", [])
            }
            current.update(
                {
                    item.ingredient_id: item.model_dump(mode="json")
                    for item in payload.package_overrides
                }
            )
            request_data["package_overrides"] = list(current.values())
        request = PlanGenerationRequest.model_validate(request_data)
        candidates = [GeneratedRecipeCandidate.model_validate(item) for item in preview.candidates]
        slots = self._meal_slots(request)
        profile, ingredients, package_options, storage_rules, pantry_items = (
            await self._planning_inputs(request)
        )
        pinned = {item.slot_key: item.candidate_id for item in payload.pinned_choices}
        solution = self.optimizer.solve(
            request=request,
            profile=profile,
            meal_slots=slots,
            candidates=candidates,
            ingredients=ingredients,
            pantry_items=pantry_items,
            package_options=package_options,
            storage_rules=storage_rules,
            pinned_choices=pinned,
        )
        return await self.previews.update(
            preview_id,
            {"request": request.model_dump(mode="json"), "solution": solution},
        )

    async def confirm(self, preview_id: UUID) -> dict[str, Any]:
        preview = await self.previews.get_for_update(preview_id)
        if preview.confirmed_plan_id is not None:
            return await self._confirmed_result(preview.confirmed_plan_id)
        self._ensure_active(preview)
        if preview.solution.get("confirmation_blocked"):
            raise ConflictError(
                "This preview needs price overrides before confirmation",
                details={"reasons": preview.solution.get("confirmation_blockers", [])},
            )

        request = PlanGenerationRequest.model_validate(preview.request)
        candidates = {
            item.candidate_id: item
            for item in (GeneratedRecipeCandidate.model_validate(value) for value in preview.candidates)
        }
        selected_ids = list(
            dict.fromkeys(item["candidate_id"] for item in preview.solution["assignments"])
        )
        persisted_recipes = {}
        for candidate_id in selected_ids:
            candidate = candidates[candidate_id]
            recipe = await self.recipes.create(
                {
                    "title": candidate.title,
                    "description": candidate.description,
                    "source": "generated",
                    "cuisine": candidate.cuisine,
                    "category": candidate.category,
                    "servings": Decimal(candidate.servings),
                    "prep_minutes": candidate.prep_minutes,
                    "cook_minutes": candidate.cook_minutes,
                    "instructions": candidate.instructions,
                    "nutrition": {
                        "calories_per_serving": candidate.calories_per_serving,
                        "protein_g_per_serving": candidate.protein_g_per_serving,
                        "estimated": True,
                    },
                    "preference_tags": candidate.style_tags + candidate.taste_tags,
                    "generation_metadata": {
                        "candidate_id": candidate_id,
                        "prompt_version": preview.prompt_version,
                        "model": preview.model,
                        "generated_from_preview_id": str(preview.id),
                    },
                    "saved_at": datetime.now(UTC),
                },
                [
                    {
                        **item.model_dump(mode="json"),
                        "quantity": Decimal(str(item.quantity)),
                    }
                    for item in candidate.ingredients
                ],
            )
            persisted_recipes[candidate_id] = recipe

        assignments = preview.solution["assignments"]
        plan = await self.plans.create(
            {
                "name": "Today's waste-first plan" if request.horizon == "today" else "Waste-first weekly plan",
                "start_date": request.start_date,
                "end_date": request.start_date + timedelta(days=0 if request.horizon == "today" else 6),
                "checkout_budget": request.checkout_budget,
                "currency_code": request.currency_code,
                "selected_meal_types": [str(item) for item in request.meal_types],
                "status": "ready",
                "planning_request": request.model_dump(mode="json"),
                "optimizer_summary": preview.solution["metrics"],
            },
            [
                {
                    "meal_date": date.fromisoformat(item["meal_date"]),
                    "meal_type": item["meal_type"],
                    "recipe_id": persisted_recipes[item["candidate_id"]].id,
                    "servings": Decimal(str(item["consumed_servings"])),
                    "status": "accepted",
                    "preparation_mode": item["preparation_mode"],
                    "prepared_servings": Decimal(str(item["prepared_servings"])),
                    "consumed_servings": Decimal(str(item["consumed_servings"])),
                }
                for item in assignments
            ],
        )
        slot_meals = {
            f"{meal.meal_date}:{meal.meal_type}": meal for meal in plan.meals
        }
        for assignment in assignments:
            if assignment["source_slot_key"]:
                slot_meals[assignment["slot_key"]].source_meal_id = slot_meals[
                    assignment["source_slot_key"]
                ].id
        await self.session.flush()

        shopping_rows = []
        for item in preview.solution["shopping"]:
            shopping_rows.append(
                {
                    "ingredient_id": item["ingredient_id"],
                    "custom_label": item["ingredient_name"],
                    "required_quantity": Decimal(str(item["required_quantity"])),
                    "pantry_quantity": Decimal(str(item["pantry_quantity"])),
                    "to_buy_quantity": Decimal(str(item["to_buy_quantity"])),
                    "unit": item["unit"],
                    "needed_by_date": request.start_date,
                    "estimated_price": (
                        None if item["estimated_price"] is None else Decimal(str(item["estimated_price"]))
                    ),
                    "package_quantity": Decimal(str(item["package_quantity"])),
                    "package_count": item["package_count"],
                    "projected_leftover_quantity": Decimal(
                        str(item["projected_remainder_quantity"])
                    ),
                    "price_source": item["price_source"],
                    "storage_action": item["storage_action"],
                }
            )
        estimated_total = preview.solution["metrics"]["estimated_purchase_cost"]
        await self.shopping_lists.create_for_plan(
            plan_id=plan.id,
            currency_code=request.currency_code,
            estimated_total=None if estimated_total is None else Decimal(str(estimated_total)),
            items=shopping_rows,
        )
        await self.previews.update(
            preview_id,
            {
                "status": "confirmed",
                "confirmed_plan_id": plan.id,
                "request": {},
                "candidates": [],
                "solution": {
                    "confirmed_plan_id": plan.id,
                    "metrics": preview.solution["metrics"],
                },
            },
        )
        return await self._confirmed_result(plan.id)

    async def _confirmed_result(self, plan_id: int) -> dict[str, Any]:
        plan = await self.plans.get(plan_id)
        shopping_list = await self.shopping_lists.get_for_plan(plan_id)
        recipe_ids = list(dict.fromkeys(meal.recipe_id for meal in plan.meals if meal.recipe_id))
        recipes = await self.recipes.get_many(recipe_ids)
        return {"meal_plan": plan, "shopping_list": shopping_list, "recipes": recipes}


class ShoppingListService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = ShoppingListRepository(session, user_id)

    async def list(self, *, limit: int, offset: int):
        return await self.repo.list(limit=limit, offset=offset)

    async def get(self, list_id: int):
        return await self.repo.get(list_id)

    async def update_item(self, list_id: int, item_id: int, payload: ShoppingListItemPatch):
        return await self.repo.update_item(list_id, item_id, payload.model_dump(exclude_unset=True))


class ReceiptService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.repo = ReceiptRepository(session, user_id)

    async def list(self, *, limit: int, offset: int):
        return await self.repo.list(limit=limit, offset=offset)

    async def get(self, receipt_id: int):
        return await self.repo.get(receipt_id)

    async def create(self, payload: ReceiptCreate):
        return await self.repo.create(payload.model_dump(exclude_none=True))

    async def update(self, receipt_id: int, payload: ReceiptPatch):
        receipt = await self.repo.get(receipt_id)
        if receipt.status == "confirmed":
            raise ConflictError("Confirmed receipts cannot be edited")
        return await self.repo.update(receipt_id, payload.model_dump(exclude_unset=True))

    async def replace_extraction(self, receipt_id: int, payload: ReceiptExtraction):
        receipt = await self.repo.get(receipt_id)
        if receipt.status == "confirmed":
            raise ConflictError("Confirmed receipt items cannot be replaced")
        receipt_values = payload.model_dump(exclude={"items"}, exclude_none=True)
        receipt_values["status"] = "review"
        receipt_values["failure_reason"] = None
        items = [item.model_dump(exclude_none=True) for item in payload.items]
        return await self.repo.replace_items(receipt_id, receipt_values, items)

    async def confirm(self, receipt_id: int):
        try:
            await self.session.execute(text("select public.confirm_receipt(:receipt_id)"), {"receipt_id": receipt_id})
            await self.session.flush()
        except DBAPIError as exc:
            _translate_workflow_error(exc)
        return await self.repo.get(receipt_id)

    async def delete(self, receipt_id: int) -> None:
        receipt = await self.repo.get(receipt_id)
        if receipt.status == "confirmed":
            raise ConflictError("Confirmed receipts cannot be deleted because they source pantry items")
        await self.repo.delete(receipt_id)


class WasteService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.repo = WasteRepository(session, user_id)

    async def list(self, *, limit: int, offset: int):
        return await self.repo.list(limit=limit, offset=offset)

    async def create(self, payload: WasteEventCreate):
        parameters = {
            "pantry_item_id": payload.pantry_item_id,
            "quantity": payload.quantity,
            "reason": payload.reason.value,
        }
        if payload.occurred_at is None:
            statement = text(
                "select public.record_waste(:pantry_item_id, :quantity, :reason)"
            )
        else:
            statement = text(
                "select public.record_waste(:pantry_item_id, :quantity, :reason, :occurred_at)"
            )
            parameters["occurred_at"] = payload.occurred_at
        try:
            event_id = await self.session.scalar(statement, parameters)
            await self.session.flush()
        except DBAPIError as exc:
            _translate_workflow_error(exc)
        return await self.repo.get(int(event_id))
