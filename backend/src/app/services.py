from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import ConflictError, ValidationError
from .repositories import (
    IngredientRepository,
    MealPlanRepository,
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
    PantryItemCreate,
    PantryItemPatch,
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
        return await self.repo.update(payload.model_dump(exclude_unset=True))


class IngredientService:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.repo = IngredientRepository(session, user_id)

    async def list(self, **kwargs):
        return await self.repo.list(**kwargs)


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
