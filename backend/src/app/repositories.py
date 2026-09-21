from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .errors import NotFoundError
from .models import (
    Ingredient,
    IngredientPackageOption,
    IngredientStorageRule,
    MealPlan,
    MealPlanGenerationPreview,
    MealPlanMeal,
    PantryItem,
    Profile,
    Receipt,
    ReceiptItem,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    WasteEvent,
)


ModelT = TypeVar("ModelT")


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id


class ProfileRepository(Repository[Profile]):
    async def get(self) -> Profile:
        profile = await self.session.get(Profile, self.user_id)
        if profile is None:
            raise NotFoundError("Profile not found")
        return profile

    async def update(self, values: dict[str, Any]) -> Profile:
        profile = await self.get()
        for field, value in values.items():
            setattr(profile, field, value)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def complete_onboarding(self, values: dict[str, Any]) -> Profile:
        profile = await self.get()
        for field, value in values.items():
            setattr(profile, field, value)
        if profile.onboarding_completed_at is None:
            profile.onboarding_completed_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile


class IngredientRepository(Repository[Ingredient]):
    async def list(
        self,
        *,
        query: str | None,
        dietary_tag: str | None,
        allergen: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Ingredient], int]:
        filters = []
        if query:
            filters.append(Ingredient.name.ilike(f"%{query.strip()}%"))
        if dietary_tag:
            filters.append(Ingredient.dietary_tags.contains([dietary_tag]))
        if allergen:
            filters.append(Ingredient.allergens.contains([allergen]))
        statement = select(Ingredient).where(*filters)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.scalars(
            statement.order_by(Ingredient.name, Ingredient.id).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def require(self, ingredient_id: int) -> Ingredient:
        ingredient = await self.session.get(Ingredient, ingredient_id)
        if ingredient is None:
            raise NotFoundError("Ingredient not found")
        return ingredient

    async def all(self) -> list[Ingredient]:
        rows = await self.session.scalars(select(Ingredient).order_by(Ingredient.name))
        return list(rows)

    async def package_options(self) -> list[IngredientPackageOption]:
        rows = await self.session.scalars(
            select(IngredientPackageOption).order_by(
                IngredientPackageOption.ingredient_id,
                IngredientPackageOption.is_default.desc(),
                IngredientPackageOption.quantity,
            )
        )
        return list(rows)

    async def storage_rules(self) -> list[IngredientStorageRule]:
        rows = await self.session.scalars(
            select(IngredientStorageRule).order_by(
                IngredientStorageRule.ingredient_id,
                IngredientStorageRule.storage_state,
            )
        )
        return list(rows)

    async def receipt_unit_prices(self) -> dict[int, tuple[float, str]]:
        rows = await self.session.execute(
            select(
                ReceiptItem.ingredient_id,
                (ReceiptItem.line_total / ReceiptItem.quantity).label("unit_price"),
                Receipt.currency_code,
                Receipt.purchased_at,
            )
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(
                Receipt.user_id == self.user_id,
                Receipt.status == "confirmed",
                ReceiptItem.ingredient_id.is_not(None),
                ReceiptItem.line_total.is_not(None),
                ReceiptItem.quantity.is_not(None),
                ReceiptItem.quantity > 0,
            )
            .order_by(ReceiptItem.ingredient_id, Receipt.purchased_at.desc().nulls_last())
        )
        prices: dict[int, tuple[float, str]] = {}
        for ingredient_id, unit_price, currency_code, _ in rows:
            prices.setdefault(int(ingredient_id), (float(unit_price), currency_code))
        return prices


class IngredientStorageRuleRepository(Repository[IngredientStorageRule]):
    async def list_for_ingredient(self, ingredient_id: int) -> list[IngredientStorageRule]:
        rows = await self.session.scalars(
            select(IngredientStorageRule)
            .where(IngredientStorageRule.ingredient_id == ingredient_id)
            .order_by(IngredientStorageRule.ingredient_id, IngredientStorageRule.storage_state)
        )
        return list(rows)

    async def list_for_ingredients(self, ingredient_ids: set[int]) -> list[IngredientStorageRule]:
        if not ingredient_ids:
            return []
        rows = await self.session.scalars(
            select(IngredientStorageRule).where(
                IngredientStorageRule.ingredient_id.in_(ingredient_ids)
            )
        )
        return list(rows)


class PantryRepository(Repository[PantryItem]):
    _options = (selectinload(PantryItem.ingredient),)

    async def list(
        self,
        *,
        status: str | None,
        best_before_lte: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PantryItem], int]:
        filters = [PantryItem.user_id == self.user_id]
        if status:
            filters.append(PantryItem.status == status)
        if best_before_lte:
            filters.append(PantryItem.best_before_on <= best_before_lte)
        statement = select(PantryItem).where(*filters)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.scalars(
            statement.options(*self._options)
            .order_by(PantryItem.best_before_on.asc().nulls_last(), PantryItem.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, item_id: int) -> PantryItem:
        item = await self.session.scalar(
            select(PantryItem)
            .where(PantryItem.id == item_id, PantryItem.user_id == self.user_id)
            .options(*self._options)
        )
        if item is None:
            raise NotFoundError("Pantry item not found")
        return item

    async def create(self, values: dict[str, Any]) -> PantryItem:
        item = PantryItem(user_id=self.user_id, **values)
        self.session.add(item)
        await self.session.flush()
        return await self.get(item.id)

    async def update(self, item_id: int, values: dict[str, Any]) -> PantryItem:
        item = await self.get(item_id)
        for field, value in values.items():
            setattr(item, field, value)
        await self.session.flush()
        return await self.get(item.id)

    async def delete(self, item_id: int) -> None:
        item = await self.get(item_id)
        await self.session.delete(item)
        await self.session.flush()


class RecipeRepository(Repository[Recipe]):
    _options = (selectinload(Recipe.ingredients),)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Recipe], int]:
        base = select(Recipe).where(Recipe.user_id == self.user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.options(*self._options)
            .order_by(Recipe.created_at.desc(), Recipe.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, recipe_id: int) -> Recipe:
        recipe = await self.session.scalar(
            select(Recipe)
            .where(Recipe.id == recipe_id, Recipe.user_id == self.user_id)
            .options(*self._options)
        )
        if recipe is None:
            raise NotFoundError("Recipe not found")
        return recipe

    async def get_many(self, recipe_ids: list[int]) -> list[Recipe]:
        if not recipe_ids:
            return []
        rows = await self.session.scalars(
            select(Recipe)
            .where(Recipe.id.in_(recipe_ids), Recipe.user_id == self.user_id)
            .options(*self._options)
            .order_by(Recipe.id)
        )
        return list(rows)

    async def create(self, values: dict[str, Any], ingredients: list[dict[str, Any]]) -> Recipe:
        recipe = Recipe(user_id=self.user_id, **values)
        self.session.add(recipe)
        await self.session.flush()
        self.session.add_all(
            RecipeIngredient(user_id=self.user_id, recipe_id=recipe.id, position=index, **item)
            for index, item in enumerate(ingredients, start=1)
        )
        await self.session.flush()
        return await self.get(recipe.id)

    async def update(
        self,
        recipe_id: int,
        values: dict[str, Any],
        ingredients: list[dict[str, Any]] | None,
    ) -> Recipe:
        recipe = await self.get(recipe_id)
        for field, value in values.items():
            setattr(recipe, field, value)
        if ingredients is not None:
            await self.session.execute(
                delete(RecipeIngredient).where(
                    RecipeIngredient.recipe_id == recipe_id,
                    RecipeIngredient.user_id == self.user_id,
                )
            )
            self.session.add_all(
                RecipeIngredient(user_id=self.user_id, recipe_id=recipe.id, position=index, **item)
                for index, item in enumerate(ingredients, start=1)
            )
        await self.session.flush()
        self.session.expire(recipe, ["ingredients"])
        return await self.get(recipe.id)

    async def delete(self, recipe_id: int) -> None:
        recipe = await self.get(recipe_id)
        await self.session.delete(recipe)
        await self.session.flush()


class MealPlanRepository(Repository[MealPlan]):
    _options = (selectinload(MealPlan.meals),)

    async def list(self, *, limit: int, offset: int) -> tuple[list[MealPlan], int]:
        base = select(MealPlan).where(MealPlan.user_id == self.user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.options(*self._options)
            .order_by(MealPlan.start_date.desc(), MealPlan.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, plan_id: int) -> MealPlan:
        plan = await self.session.scalar(
            select(MealPlan)
            .where(MealPlan.id == plan_id, MealPlan.user_id == self.user_id)
            .options(*self._options)
        )
        if plan is None:
            raise NotFoundError("Meal plan not found")
        return plan

    async def get_meal(self, plan_id: int, meal_id: int) -> MealPlanMeal:
        meal = await self.session.scalar(
            select(MealPlanMeal).where(
                MealPlanMeal.id == meal_id,
                MealPlanMeal.meal_plan_id == plan_id,
                MealPlanMeal.user_id == self.user_id,
            )
        )
        if meal is None:
            raise NotFoundError("Meal-plan slot not found")
        return meal

    async def create(self, values: dict[str, Any], meals: list[dict[str, Any]]) -> MealPlan:
        plan = MealPlan(user_id=self.user_id, **values)
        self.session.add(plan)
        await self.session.flush()
        self.session.add_all(MealPlanMeal(user_id=self.user_id, meal_plan_id=plan.id, **meal) for meal in meals)
        await self.session.flush()
        return await self.get(plan.id)

    async def update(self, plan_id: int, values: dict[str, Any]) -> MealPlan:
        plan = await self.get(plan_id)
        for field, value in values.items():
            setattr(plan, field, value)
        await self.session.flush()
        return await self.get(plan.id)

    async def update_meal(self, plan_id: int, meal_id: int, values: dict[str, Any]) -> MealPlanMeal:
        meal = await self.get_meal(plan_id, meal_id)
        for field, value in values.items():
            setattr(meal, field, value)
        await self.session.flush()
        await self.session.refresh(meal)
        return meal

    async def delete(self, plan_id: int) -> None:
        plan = await self.get(plan_id)
        await self.session.delete(plan)
        await self.session.flush()


class ShoppingListRepository(Repository[ShoppingList]):
    _options = (selectinload(ShoppingList.items),)

    async def list(self, *, limit: int, offset: int) -> tuple[list[ShoppingList], int]:
        base = select(ShoppingList).where(ShoppingList.user_id == self.user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.options(*self._options)
            .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, list_id: int) -> ShoppingList:
        shopping_list = await self.session.scalar(
            select(ShoppingList)
            .where(ShoppingList.id == list_id, ShoppingList.user_id == self.user_id)
            .options(*self._options)
        )
        if shopping_list is None:
            raise NotFoundError("Shopping list not found")
        return shopping_list

    async def get_for_plan(self, plan_id: int) -> ShoppingList:
        shopping_list = await self.session.scalar(
            select(ShoppingList)
            .where(ShoppingList.meal_plan_id == plan_id, ShoppingList.user_id == self.user_id)
            .options(*self._options)
        )
        if shopping_list is None:
            raise NotFoundError("Shopping list not found")
        return shopping_list

    async def update_item(self, list_id: int, item_id: int, values: dict[str, Any]) -> ShoppingListItem:
        item = await self.session.scalar(
            select(ShoppingListItem).where(
                ShoppingListItem.id == item_id,
                ShoppingListItem.shopping_list_id == list_id,
                ShoppingListItem.user_id == self.user_id,
            )
        )
        if item is None:
            raise NotFoundError("Shopping-list item not found")
        for field, value in values.items():
            setattr(item, field, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def create_for_plan(
        self,
        *,
        plan_id: int,
        currency_code: str,
        estimated_total,
        items: list[dict[str, Any]],
    ) -> ShoppingList:
        shopping_list = ShoppingList(
            user_id=self.user_id,
            meal_plan_id=plan_id,
            currency_code=currency_code,
            estimated_total=estimated_total,
            status="active",
            calculated_at=datetime.now(UTC),
        )
        self.session.add(shopping_list)
        await self.session.flush()
        self.session.add_all(
            ShoppingListItem(
                user_id=self.user_id,
                shopping_list_id=shopping_list.id,
                source="generated",
                status="pending",
                **item,
            )
            for item in items
        )
        await self.session.flush()
        return await self.get(shopping_list.id)


class MealPlanPreviewRepository(Repository[MealPlanGenerationPreview]):
    async def delete_expired(self) -> None:
        await self.session.execute(
            delete(MealPlanGenerationPreview).where(
                MealPlanGenerationPreview.user_id == self.user_id,
                MealPlanGenerationPreview.expires_at <= datetime.now(UTC),
                MealPlanGenerationPreview.confirmed_plan_id.is_(None),
            )
        )

    async def create(self, values: dict[str, Any]) -> MealPlanGenerationPreview:
        preview = MealPlanGenerationPreview(user_id=self.user_id, **values)
        self.session.add(preview)
        await self.session.flush()
        await self.session.refresh(preview)
        return preview

    async def get(self, preview_id: UUID) -> MealPlanGenerationPreview:
        preview = await self.session.scalar(
            select(MealPlanGenerationPreview).where(
                MealPlanGenerationPreview.id == preview_id,
                MealPlanGenerationPreview.user_id == self.user_id,
            )
        )
        if preview is None:
            raise NotFoundError("Meal-plan preview not found")
        return preview

    async def get_for_update(self, preview_id: UUID) -> MealPlanGenerationPreview:
        preview = await self.session.scalar(
            select(MealPlanGenerationPreview)
            .where(
                MealPlanGenerationPreview.id == preview_id,
                MealPlanGenerationPreview.user_id == self.user_id,
            )
            .with_for_update()
        )
        if preview is None:
            raise NotFoundError("Meal-plan preview not found")
        return preview

    async def update(self, preview_id: UUID, values: dict[str, Any]) -> MealPlanGenerationPreview:
        preview = await self.get(preview_id)
        for field, value in values.items():
            setattr(preview, field, value)
        await self.session.flush()
        await self.session.refresh(preview)
        return preview


class ReceiptRepository(Repository[Receipt]):
    _options = (selectinload(Receipt.items),)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Receipt], int]:
        base = select(Receipt).where(Receipt.user_id == self.user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.options(*self._options)
            .order_by(Receipt.created_at.desc(), Receipt.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, receipt_id: int) -> Receipt:
        receipt = await self.session.scalar(
            select(Receipt)
            .where(Receipt.id == receipt_id, Receipt.user_id == self.user_id)
            .options(*self._options)
        )
        if receipt is None:
            raise NotFoundError("Receipt not found")
        return receipt

    async def create(self, values: dict[str, Any]) -> Receipt:
        receipt = Receipt(user_id=self.user_id, raw_ocr={}, status="uploaded", **values)
        self.session.add(receipt)
        await self.session.flush()
        return await self.get(receipt.id)

    async def update(self, receipt_id: int, values: dict[str, Any]) -> Receipt:
        receipt = await self.get(receipt_id)
        for field, value in values.items():
            setattr(receipt, field, value)
        await self.session.flush()
        return await self.get(receipt.id)

    async def replace_items(
        self,
        receipt_id: int,
        receipt_values: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> Receipt:
        receipt = await self.get(receipt_id)
        await self.session.execute(
            delete(ReceiptItem).where(
                ReceiptItem.receipt_id == receipt_id,
                ReceiptItem.user_id == self.user_id,
            )
        )
        for field, value in receipt_values.items():
            setattr(receipt, field, value)
        self.session.add_all(
            ReceiptItem(user_id=self.user_id, receipt_id=receipt_id, **item) for item in items
        )
        await self.session.flush()
        self.session.expire(receipt, ["items"])
        return await self.get(receipt.id)

    async def delete(self, receipt_id: int) -> None:
        receipt = await self.get(receipt_id)
        await self.session.delete(receipt)
        await self.session.flush()


class WasteRepository(Repository[WasteEvent]):
    async def list(self, *, limit: int, offset: int) -> tuple[list[WasteEvent], int]:
        base = select(WasteEvent).where(WasteEvent.user_id == self.user_id)
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self.session.scalars(
            base.order_by(WasteEvent.occurred_at.desc(), WasteEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def get(self, event_id: int) -> WasteEvent:
        event = await self.session.scalar(
            select(WasteEvent).where(WasteEvent.id == event_id, WasteEvent.user_id == self.user_id)
        )
        if event is None:
            raise NotFoundError("Waste event not found")
        return event
