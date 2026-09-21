from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.app.schemas import MealPlanCreate, MealType, ProfilePatch
from src.app.services import MealPlanService, ProfileService


@pytest.mark.asyncio
async def test_meal_plan_creation_expands_dates_and_meal_types() -> None:
    service = MealPlanService(AsyncMock(), uuid4())
    service.repo.create = AsyncMock(return_value="created")
    payload = MealPlanCreate(
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 22),
        selected_meal_types=[MealType.LUNCH, MealType.DINNER],
    )

    result = await service.create(payload)

    assert result == "created"
    values, meals = service.repo.create.await_args.args
    assert values["selected_meal_types"] == ["lunch", "dinner"]
    assert [(meal["meal_date"], meal["meal_type"]) for meal in meals] == [
        (date(2026, 9, 21), "lunch"),
        (date(2026, 9, 21), "dinner"),
        (date(2026, 9, 22), "lunch"),
        (date(2026, 9, 22), "dinner"),
    ]


@pytest.mark.asyncio
async def test_profile_patch_updates_only_supplied_preferences() -> None:
    service = ProfileService(AsyncMock(), uuid4())
    service.repo.update = AsyncMock(return_value="updated")

    result = await service.update(ProfilePatch(preferred_tastes=[" Fresh "]))

    assert result == "updated"
    service.repo.update.assert_awaited_once_with({"preferred_tastes": ["fresh"]})
