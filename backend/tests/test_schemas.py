from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.app.schemas import MealPlanCreate, PantryItemCreate, ReceiptExtraction, ReceiptItemInput


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
