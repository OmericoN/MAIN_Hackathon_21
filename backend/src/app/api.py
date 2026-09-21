from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, get_principal
from .database import get_user_session
from .schemas import (
    HealthResponse,
    IngredientStorageRuleRead,
    IngredientRead,
    MealPlanCreate,
    MealPlanPatch,
    MealPlanRead,
    MealSlotPatch,
    MealSlotRead,
    OnboardingPut,
    Page,
    PantryItemCreate,
    PantryItemPatch,
    PantryItemRead,
    PantryStatus,
    ProfilePatch,
    ProfileRead,
    ReceiptCreate,
    ReceiptExtraction,
    ReceiptPatch,
    ReceiptRead,
    RecipeCreate,
    RecipePatch,
    RecipeRead,
    ShoppingListItemPatch,
    ShoppingListItemRead,
    ShoppingListRead,
    WasteEventCreate,
    WasteEventRead,
)
from .services import (
    IngredientService,
    MealPlanService,
    PantryService,
    ProfileService,
    ReceiptService,
    RecipeService,
    ShoppingListService,
    WasteService,
)


router = APIRouter(prefix="/v1")
SessionDep = Annotated[AsyncSession, Depends(get_user_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def page(items, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/me/profile", response_model=ProfileRead)
async def get_profile(session: SessionDep, principal: PrincipalDep):
    return await ProfileService(session, principal.user_id).get()


@router.patch("/me/profile", response_model=ProfileRead)
async def update_profile(payload: ProfilePatch, session: SessionDep, principal: PrincipalDep):
    return await ProfileService(session, principal.user_id).update(payload)


@router.put("/me/onboarding", response_model=ProfileRead)
async def complete_onboarding(
    payload: OnboardingPut, session: SessionDep, principal: PrincipalDep
):
    return await ProfileService(session, principal.user_id).complete_onboarding(payload)


@router.get("/ingredients", response_model=Page[IngredientRead])
async def list_ingredients(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Limit = 50,
    offset: Offset = 0,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    dietary_tag: str | None = Query(default=None, min_length=1, max_length=100),
    allergen: str | None = Query(default=None, min_length=1, max_length=100),
):
    items, total = await IngredientService(session, principal.user_id).list(
        query=q, dietary_tag=dietary_tag, allergen=allergen, limit=limit, offset=offset
    )
    return page(items, total, limit, offset)


@router.get("/ingredients/{ingredient_id}/storage-rules", response_model=list[IngredientStorageRuleRead])
async def list_ingredient_storage_rules(
    ingredient_id: int, session: SessionDep, principal: PrincipalDep
):
    return await IngredientService(session, principal.user_id).storage_rules(ingredient_id)


@router.get("/pantry-items/expiring", response_model=Page[PantryItemRead])
async def list_expiring_pantry_items(
    session: SessionDep,
    principal: PrincipalDep,
    days: int = Query(default=7, ge=0, le=90),
    limit: Limit = 50,
    offset: Offset = 0,
):
    items, total = await PantryService(session, principal.user_id).expiring(days, limit, offset)
    return page(items, total, limit, offset)


@router.get("/pantry-items", response_model=Page[PantryItemRead])
async def list_pantry_items(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Limit = 50,
    offset: Offset = 0,
    item_status: PantryStatus | None = Query(default=None, alias="status"),
):
    items, total = await PantryService(session, principal.user_id).list(
        status=item_status, best_before_lte=None, limit=limit, offset=offset
    )
    return page(items, total, limit, offset)


@router.post("/pantry-items", response_model=PantryItemRead, status_code=status.HTTP_201_CREATED)
async def create_pantry_item(payload: PantryItemCreate, session: SessionDep, principal: PrincipalDep):
    return await PantryService(session, principal.user_id).create(payload)


@router.get("/pantry-items/{item_id}", response_model=PantryItemRead)
async def get_pantry_item(item_id: int, session: SessionDep, principal: PrincipalDep):
    return await PantryService(session, principal.user_id).get(item_id)


@router.patch("/pantry-items/{item_id}", response_model=PantryItemRead)
async def update_pantry_item(
    item_id: int, payload: PantryItemPatch, session: SessionDep, principal: PrincipalDep
):
    return await PantryService(session, principal.user_id).update(item_id, payload)


@router.delete("/pantry-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pantry_item(item_id: int, session: SessionDep, principal: PrincipalDep) -> Response:
    await PantryService(session, principal.user_id).delete(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/recipes", response_model=Page[RecipeRead])
async def list_recipes(
    session: SessionDep, principal: PrincipalDep, limit: Limit = 50, offset: Offset = 0
):
    items, total = await RecipeService(session, principal.user_id).list(limit=limit, offset=offset)
    return page(items, total, limit, offset)


@router.post("/recipes", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
async def create_recipe(payload: RecipeCreate, session: SessionDep, principal: PrincipalDep):
    return await RecipeService(session, principal.user_id).create(payload)


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
async def get_recipe(recipe_id: int, session: SessionDep, principal: PrincipalDep):
    return await RecipeService(session, principal.user_id).get(recipe_id)


@router.patch("/recipes/{recipe_id}", response_model=RecipeRead)
async def update_recipe(
    recipe_id: int, payload: RecipePatch, session: SessionDep, principal: PrincipalDep
):
    return await RecipeService(session, principal.user_id).update(recipe_id, payload)


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(recipe_id: int, session: SessionDep, principal: PrincipalDep) -> Response:
    await RecipeService(session, principal.user_id).delete(recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/meal-plans", response_model=Page[MealPlanRead])
async def list_meal_plans(
    session: SessionDep, principal: PrincipalDep, limit: Limit = 50, offset: Offset = 0
):
    items, total = await MealPlanService(session, principal.user_id).list(limit=limit, offset=offset)
    return page(items, total, limit, offset)


@router.post("/meal-plans", response_model=MealPlanRead, status_code=status.HTTP_201_CREATED)
async def create_meal_plan(payload: MealPlanCreate, session: SessionDep, principal: PrincipalDep):
    return await MealPlanService(session, principal.user_id).create(payload)


@router.get("/meal-plans/{plan_id}", response_model=MealPlanRead)
async def get_meal_plan(plan_id: int, session: SessionDep, principal: PrincipalDep):
    return await MealPlanService(session, principal.user_id).get(plan_id)


@router.patch("/meal-plans/{plan_id}", response_model=MealPlanRead)
async def update_meal_plan(
    plan_id: int, payload: MealPlanPatch, session: SessionDep, principal: PrincipalDep
):
    return await MealPlanService(session, principal.user_id).update(plan_id, payload)


@router.patch("/meal-plans/{plan_id}/meals/{meal_id}", response_model=MealSlotRead)
async def update_meal_slot(
    plan_id: int,
    meal_id: int,
    payload: MealSlotPatch,
    session: SessionDep,
    principal: PrincipalDep,
):
    return await MealPlanService(session, principal.user_id).update_meal(plan_id, meal_id, payload)


@router.post("/meal-plans/{plan_id}/shopping-list/rebuild", response_model=ShoppingListRead)
async def rebuild_shopping_list(plan_id: int, session: SessionDep, principal: PrincipalDep):
    return await MealPlanService(session, principal.user_id).rebuild_shopping_list(plan_id)


@router.delete("/meal-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal_plan(plan_id: int, session: SessionDep, principal: PrincipalDep) -> Response:
    await MealPlanService(session, principal.user_id).delete(plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/shopping-lists", response_model=Page[ShoppingListRead])
async def list_shopping_lists(
    session: SessionDep, principal: PrincipalDep, limit: Limit = 50, offset: Offset = 0
):
    items, total = await ShoppingListService(session, principal.user_id).list(limit=limit, offset=offset)
    return page(items, total, limit, offset)


@router.get("/shopping-lists/{list_id}", response_model=ShoppingListRead)
async def get_shopping_list(list_id: int, session: SessionDep, principal: PrincipalDep):
    return await ShoppingListService(session, principal.user_id).get(list_id)


@router.patch("/shopping-lists/{list_id}/items/{item_id}", response_model=ShoppingListItemRead)
async def update_shopping_list_item(
    list_id: int,
    item_id: int,
    payload: ShoppingListItemPatch,
    session: SessionDep,
    principal: PrincipalDep,
):
    return await ShoppingListService(session, principal.user_id).update_item(list_id, item_id, payload)


@router.get("/receipts", response_model=Page[ReceiptRead])
async def list_receipts(
    session: SessionDep, principal: PrincipalDep, limit: Limit = 50, offset: Offset = 0
):
    items, total = await ReceiptService(session, principal.user_id).list(limit=limit, offset=offset)
    return page(items, total, limit, offset)


@router.post("/receipts", response_model=ReceiptRead, status_code=status.HTTP_201_CREATED)
async def create_receipt(payload: ReceiptCreate, session: SessionDep, principal: PrincipalDep):
    return await ReceiptService(session, principal.user_id).create(payload)


@router.get("/receipts/{receipt_id}", response_model=ReceiptRead)
async def get_receipt(receipt_id: int, session: SessionDep, principal: PrincipalDep):
    return await ReceiptService(session, principal.user_id).get(receipt_id)


@router.patch("/receipts/{receipt_id}", response_model=ReceiptRead)
async def update_receipt(
    receipt_id: int, payload: ReceiptPatch, session: SessionDep, principal: PrincipalDep
):
    return await ReceiptService(session, principal.user_id).update(receipt_id, payload)


@router.put("/receipts/{receipt_id}/extraction", response_model=ReceiptRead)
async def replace_receipt_extraction(
    receipt_id: int,
    payload: ReceiptExtraction,
    session: SessionDep,
    principal: PrincipalDep,
):
    return await ReceiptService(session, principal.user_id).replace_extraction(receipt_id, payload)


@router.post("/receipts/{receipt_id}/confirm", response_model=ReceiptRead)
async def confirm_receipt(receipt_id: int, session: SessionDep, principal: PrincipalDep):
    return await ReceiptService(session, principal.user_id).confirm(receipt_id)


@router.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(receipt_id: int, session: SessionDep, principal: PrincipalDep) -> Response:
    await ReceiptService(session, principal.user_id).delete(receipt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/waste-events", response_model=Page[WasteEventRead])
async def list_waste_events(
    session: SessionDep, principal: PrincipalDep, limit: Limit = 50, offset: Offset = 0
):
    items, total = await WasteService(session, principal.user_id).list(limit=limit, offset=offset)
    return page(items, total, limit, offset)


@router.post("/waste-events", response_model=WasteEventRead, status_code=status.HTTP_201_CREATED)
async def create_waste_event(payload: WasteEventCreate, session: SessionDep, principal: PrincipalDep):
    return await WasteService(session, principal.user_id).create(payload)
