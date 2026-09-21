from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.app.schemas import (
    MealPlanCreate,
    OnboardingPut,
    PantryItemCreate,
    ProfilePatch,
    ReceiptExtraction,
    ReceiptItemInput,
)


def test_onboarding_normalizes_minimal_preferences() -> None:
    payload = OnboardingPut.model_validate(
        {
            "display_name": "Ada",
            "dietary_preferences": [" Vegetarian "],
            "allergies": [" Milk "],
            "preferred_cuisines": [" Italian "],
            "preferred_tastes": [" Umami "],
            "daily_calorie_target": 2_000,
        }
    )

    assert payload.dietary_preferences == ["vegetarian"]
    assert payload.allergies == ["milk"]
    assert payload.preferred_cuisines == ["italian"]
    assert payload.preferred_tastes == ["umami"]


def test_onboarding_allows_empty_and_omitted_preferences() -> None:
    assert OnboardingPut().model_dump() == {
        "display_name": None,
        "dietary_preferences": [],
        "allergies": [],
        "preferred_cuisines": [],
        "preferred_tastes": [],
        "daily_calorie_target": None,
    }


@pytest.mark.parametrize(
    "values",
    [
        {"preferred_tastes": ["spicy", " SPICY "]},
        {"preferred_cuisines": ["  "]},
        {"dietary_preferences": ["x" * 101]},
        {"allergies": ["strawberries"]},
        {"daily_calorie_target": 499},
        {"daily_calorie_target": 10_001},
    ],
)
def test_onboarding_rejects_invalid_preferences(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OnboardingPut.model_validate(values)


def test_profile_patch_rejects_explicit_null_preference_lists() -> None:
    with pytest.raises(ValidationError):
        ProfilePatch(preferred_tastes=None)


def test_meal_plan_rejects_more_than_32_calendar_days() -> None:
    with pytest.raises(ValidationError):
        MealPlanCreate(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 3),
            selected_meal_types=["dinner"],
        )


def test_pantry_item_defaults_remaining_quantity_in_service_but_validates_upper_bound() -> None:
    with pytest.raises(ValidationError):
        PantryItemCreate(
            ingredient_id=1,
            initial_quantity=Decimal("2"),
            remaining_quantity=Decimal("3"),
            unit="each",
        )


def test_receipt_extraction_requires_unique_line_numbers() -> None:
    line = ReceiptItemInput(line_number=1, raw_text="Tomatoes")
    with pytest.raises(ValidationError):
        ReceiptExtraction(items=[line, line])
