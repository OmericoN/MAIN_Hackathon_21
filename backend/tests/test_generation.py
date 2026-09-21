from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.app.errors import GenerationError, GenerationUnavailableError
from src.app.generation import OpenAIRecipeGenerator, build_generation_context, validate_candidates
from src.app.schemas import GeneratedRecipeBatch, MealType, PlanGenerationRequest


def ingredient(**overrides):
    values = {
        "id": 1,
        "name": "Ground beef",
        "base_unit": "g",
        "dietary_tags": [],
        "allergens": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def request(**overrides):
    values = {
        "horizon": "today",
        "start_date": date(2026, 9, 21),
        "meal_types": ["dinner"],
        "household_servings": 2,
    }
    values.update(overrides)
    return PlanGenerationRequest(**values)


def batch(**ingredient_overrides):
    item = {"ingredient_id": 1, "quantity": 300, "unit": "g"}
    item.update(ingredient_overrides)
    return GeneratedRecipeBatch.model_validate(
        {
            "recipes": [
                {
                    "candidate_id": "beef-bowl",
                    "title": "Glossy beef bowl",
                    "description": "Fast and deeply savory.",
                    "cuisine": "korean-inspired",
                    "category": "dinner",
                    "eligible_meal_types": ["dinner"],
                    "style_tags": ["stir-fry"],
                    "taste_tags": ["savory"],
                    "servings": 2,
                    "prep_minutes": 10,
                    "cook_minutes": 15,
                    "instructions": ["Cook until safely done."],
                    "ingredients": [item],
                }
            ]
        }
    )


def test_generation_context_excludes_unrelated_personal_data() -> None:
    profile = SimpleNamespace(
        display_name="Private Name",
        email="private@example.com",
        dietary_preferences=[],
        allergies=[],
        preferred_cuisines=["korean"],
        preferred_tastes=["savory"],
        daily_calorie_target=2000,
    )
    context = build_generation_context(
        profile=profile,
        request=request(),
        meal_slots=[{"slot_key": "2026-09-21:dinner"}],
        pantry_items=[],
        ingredients=[ingredient()],
        package_options=[],
        storage_rules=[],
        candidate_count=6,
    )

    serialized = str(context)
    assert "Private Name" not in serialized
    assert "private@example.com" not in serialized
    assert context["candidate_count"] == 6


@pytest.mark.parametrize(
    ("candidate_batch", "profile", "message"),
    [
        (batch(ingredient_id=999), SimpleNamespace(allergies=[], dietary_preferences=[]), "unknown"),
        (
            batch(ingredient_id=1),
            SimpleNamespace(allergies=["soybeans"], dietary_preferences=[]),
            "allergies",
        ),
        (batch(unit="ml"), SimpleNamespace(allergies=[], dietary_preferences=[]), "instead"),
    ],
)
def test_candidate_validation_rejects_unsafe_or_noncanonical_data(
    candidate_batch, profile, message
) -> None:
    catalog = [ingredient(allergens=["soybeans"])]
    with pytest.raises(GenerationError, match="failed validation") as exc:
        validate_candidates(
            candidate_batch,
            request=request(),
            profile=profile,
            ingredients=catalog,
            required_meal_types={MealType.DINNER},
        )
    assert message in str(exc.value.details).casefold()


def test_candidate_validation_enforces_time_limit_and_exclusions() -> None:
    with pytest.raises(GenerationError) as exc:
        validate_candidates(
            batch(),
            request=request(max_total_minutes=20, excluded_ingredient_ids=[1]),
            profile=SimpleNamespace(allergies=[], dietary_preferences=[]),
            ingredients=[ingredient()],
            required_meal_types={MealType.DINNER},
        )
    violations = " ".join(exc.value.details["violations"])
    assert "cooking-time" in violations
    assert "excluded" in violations


@pytest.mark.asyncio
async def test_openai_parse_uses_store_false_and_one_bounded_repair() -> None:
    generator = OpenAIRecipeGenerator.__new__(OpenAIRecipeGenerator)
    generator.model = "test-model"
    generator.client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=AsyncMock(
                side_effect=[
                    SimpleNamespace(output_parsed=batch(ingredient_id=999)),
                    SimpleNamespace(output_parsed=batch()),
                ]
            )
        )
    )
    result = await generator.generate(
        context={"safe": True},
        request=request(),
        profile=SimpleNamespace(allergies=[], dietary_preferences=[]),
        ingredients=[ingredient()],
        required_meal_types={MealType.DINNER},
    )

    assert result[0].candidate_id == "beef-bowl"
    assert generator.client.responses.parse.await_count == 2
    assert all(call.kwargs["store"] is False for call in generator.client.responses.parse.await_args_list)
    repaired_prompt = generator.client.responses.parse.await_args_list[1].kwargs["input"][1]["content"]
    assert "REPAIR THE PREVIOUS RESPONSE" in repaired_prompt


@pytest.mark.asyncio
async def test_openai_timeout_is_reported_as_unavailable() -> None:
    generator = OpenAIRecipeGenerator.__new__(OpenAIRecipeGenerator)
    generator.model = "test-model"
    generator.client = SimpleNamespace(
        responses=SimpleNamespace(parse=AsyncMock(side_effect=TimeoutError("timed out")))
    )

    with pytest.raises(GenerationUnavailableError):
        await generator.generate(
            context={},
            request=request(),
            profile=SimpleNamespace(allergies=[], dietary_preferences=[]),
            ingredients=[ingredient()],
            required_meal_types={MealType.DINNER},
        )
    assert generator.client.responses.parse.await_count == 1
