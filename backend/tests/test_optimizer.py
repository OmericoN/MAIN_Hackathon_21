from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.app.errors import ConflictError
from src.app.optimizer import WasteFirstOptimizer
from src.app.schemas import GeneratedRecipeCandidate, PlanGenerationRequest


TODAY = date(2026, 9, 21)


def ingredient(
    ingredient_id: int,
    name: str,
    *,
    shelf_life: int,
    base_unit: str = "g",
):
    return SimpleNamespace(
        id=ingredient_id,
        name=name,
        base_unit=base_unit,
        density_g_per_ml=None,
        average_unit_weight_g=None,
        typical_shelf_life_days=shelf_life,
    )


def package(ingredient_id: int, quantity: int, price=None, *, can_freeze=False):
    return SimpleNamespace(
        id=ingredient_id,
        ingredient_id=ingredient_id,
        label=f"{quantity} g pack",
        quantity=quantity,
        unit="g",
        estimated_price=price,
        currency_code="EUR" if price is not None else None,
        can_freeze=can_freeze,
    )


def candidate(candidate_id: str, ingredient_id: int, quantity: int, *, tags=None):
    return GeneratedRecipeCandidate.model_validate(
        {
            "candidate_id": candidate_id,
            "title": candidate_id.replace("-", " ").title(),
            "description": "A craveable test recipe.",
            "cuisine": "fusion",
            "category": "dinner",
            "eligible_meal_types": ["dinner"],
            "style_tags": tags or [],
            "taste_tags": [],
            "servings": 1,
            "prep_minutes": 5,
            "cook_minutes": 15,
            "instructions": ["Cook."],
            "ingredients": [{"ingredient_id": ingredient_id, "quantity": quantity, "unit": "g"}],
        }
    )


def profile():
    return SimpleNamespace(
        preferred_cuisines=[], preferred_tastes=[], daily_calorie_target=None
    )


def pantry(ingredient_id: int, quantity: int, best_before: date):
    return SimpleNamespace(
        id=ingredient_id,
        ingredient_id=ingredient_id,
        remaining_quantity=quantity,
        best_before_on=best_before,
    )


def slots(days=1):
    return [
        {
            "slot_key": f"{TODAY + timedelta(days=offset)}:dinner",
            "meal_date": TODAY + timedelta(days=offset),
            "meal_type": "dinner",
        }
        for offset in range(days)
    ]


def test_waste_first_beats_more_preferred_recipe_and_uses_expiring_stock() -> None:
    beef = ingredient(1, "Ground beef", shelf_life=2)
    rice = ingredient(2, "Rice", shelf_life=365)
    request = PlanGenerationRequest(
        horizon="today",
        start_date=TODAY,
        meal_types=["dinner"],
        preferred_styles=["bowl"],
    )
    solution = WasteFirstOptimizer().solve(
        request=request,
        profile=profile(),
        meal_slots=slots(),
        candidates=[candidate("beef", 1, 600), candidate("preferred-rice", 2, 100, tags=["bowl"])],
        ingredients=[beef, rice],
        pantry_items=[pantry(1, 200, TODAY)],
        package_options=[package(1, 500, 5), package(2, 1000, 2)],
        storage_rules=[],
    )

    assert solution["assignments"][0]["candidate_id"] == "beef"
    beef_purchase = next(item for item in solution["shopping"] if item["ingredient_id"] == 1)
    assert beef_purchase["pantry_quantity"] == 200
    assert beef_purchase["projected_remainder_quantity"] == 100


def test_package_splits_across_meals_and_schedules_leftover() -> None:
    beef = ingredient(1, "Ground beef", shelf_life=2)
    request = PlanGenerationRequest(
        horizon="week",
        start_date=TODAY,
        meal_types=["dinner"],
        allow_leftovers=True,
        max_batch_portions=3,
    )
    meal_slots = slots(2)
    solution = WasteFirstOptimizer().solve(
        request=request,
        profile=profile(),
        meal_slots=meal_slots,
        candidates=[candidate("beef", 1, 250)],
        ingredients=[beef],
        pantry_items=[],
        package_options=[package(1, 500, 5)],
        storage_rules=[],
    )

    assert solution["shopping"][0]["package_count"] == 1
    assert solution["shopping"][0]["projected_remainder_quantity"] == 0
    assert solution["assignments"][0]["prepared_servings"] == 2
    assert solution["assignments"][1]["preparation_mode"] == "leftover"
    assert solution["assignments"][1]["source_slot_key"] == solution["assignments"][0]["slot_key"]


def test_budget_with_unknown_price_blocks_confirmation_and_pinned_swap_is_honored() -> None:
    beef = ingredient(1, "Ground beef", shelf_life=2)
    rice = ingredient(2, "Rice", shelf_life=365)
    request = PlanGenerationRequest(
        horizon="today",
        start_date=TODAY,
        meal_types=["dinner"],
        checkout_budget=10,
    )
    solution = WasteFirstOptimizer().solve(
        request=request,
        profile=profile(),
        meal_slots=slots(),
        candidates=[candidate("beef", 1, 250), candidate("rice", 2, 100)],
        ingredients=[beef, rice],
        pantry_items=[],
        package_options=[package(1, 500), package(2, 1000)],
        storage_rules=[],
        pinned_choices={f"{TODAY}:dinner": "rice"},
    )

    assert solution["assignments"][0]["candidate_id"] == "rice"
    assert solution["confirmation_blocked"] is True
    assert solution["metrics"]["price_complete"] is False


def test_fully_priced_budget_is_a_hard_constraint() -> None:
    beef = ingredient(1, "Ground beef", shelf_life=2)
    request = PlanGenerationRequest(
        horizon="today", start_date=TODAY, meal_types=["dinner"], checkout_budget=4
    )
    with pytest.raises(ConflictError, match="No feasible meal plan") as exc:
        WasteFirstOptimizer().solve(
            request=request,
            profile=profile(),
            meal_slots=slots(),
            candidates=[candidate("beef", 1, 250)],
            ingredients=[beef],
            pantry_items=[],
            package_options=[package(1, 500, 5)],
            storage_rules=[],
        )
    assert "budget" in str(exc.value.details).casefold()


def test_valid_freezing_rule_produces_explicit_storage_action() -> None:
    beef = ingredient(1, "Ground beef", shelf_life=2)
    solution = WasteFirstOptimizer().solve(
        request=PlanGenerationRequest(horizon="today", start_date=TODAY, meal_types=["dinner"]),
        profile=profile(),
        meal_slots=slots(),
        candidates=[candidate("beef", 1, 250)],
        ingredients=[beef],
        pantry_items=[],
        package_options=[package(1, 500, 5, can_freeze=True)],
        storage_rules=[SimpleNamespace(ingredient_id=1, freezer_shelf_life_days=90)],
    )
    assert solution["shopping"][0]["storage_action"].startswith("Freeze 250")
    assert solution["metrics"]["projected_waste_g"] == 0
