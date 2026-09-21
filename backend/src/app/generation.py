from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError as PydanticValidationError

from .errors import GenerationError, GenerationUnavailableError
from .schemas import GeneratedRecipeBatch, GeneratedRecipeCandidate, MealType, PlanGenerationRequest


SOCIAL_RECIPE_SYSTEM_PROMPT = """You are the recipe-candidate engine for a waste-first meal planner.

Generate diverse, craveable, contemporary, social-media-friendly recipes in the spirit of Mongolian
beef and rice, honey-mustard chicken, gochujang bowls, loaded wraps, glossy stir-fries, comforting
soups, and fun one-pan meals. Never claim a recipe is currently trending. Treat allergies, dietary
restrictions, exclusions, time limits, and the supplied ingredient catalog as hard constraints. Use
only supplied ingredient IDs and canonical units. Prefer soon-expiring pantry ingredients and
ingredient overlap, but preserve variety and the requested cuisines, tastes, and meal styles. Return
recipe candidates only; do not decide purchases or the final schedule.

Ingredient quantities are for the stated servings basis. Keep instructions practical and complete.
Use candidate_id values that are unique within the response. Do not include medical claims.
"""


def build_generation_context(
    *,
    profile: Any,
    request: PlanGenerationRequest,
    meal_slots: list[dict[str, Any]],
    pantry_items: Sequence[Any],
    ingredients: Sequence[Any],
    package_options: Sequence[Any],
    storage_rules: Sequence[Any],
    candidate_count: int,
) -> dict[str, Any]:
    """Build the deliberately minimized payload sent to OpenAI."""
    return {
        "profile": {
            "dietary_preferences": list(profile.dietary_preferences or []),
            "allergies": list(profile.allergies or []),
            "preferred_cuisines": list(profile.preferred_cuisines or []),
            "preferred_tastes": list(profile.preferred_tastes or []),
            "daily_calorie_target": profile.daily_calorie_target,
        },
        "request": request.model_dump(mode="json", exclude={"package_overrides"}),
        "meal_slots": meal_slots,
        "candidate_count": candidate_count,
        "pantry_batches": [
            {
                "id": item.id,
                "ingredient_id": item.ingredient_id,
                "remaining_quantity": float(item.remaining_quantity),
                "unit": item.unit,
                "best_before_on": item.best_before_on.isoformat() if item.best_before_on else None,
                "storage_location": item.storage_location,
                "storage_state": item.storage_state,
            }
            for item in pantry_items
        ],
        "ingredient_catalog": [
            {
                "id": ingredient.id,
                "name": ingredient.name,
                "canonical_unit": ingredient.base_unit,
                "dietary_tags": list(ingredient.dietary_tags or []),
                "allergens": list(ingredient.allergens or []),
            }
            for ingredient in ingredients
        ],
        "package_options": [
            {
                "ingredient_id": option.ingredient_id,
                "label": option.label,
                "quantity": float(option.quantity),
                "unit": option.unit,
                "estimated_price": (
                    None if option.estimated_price is None else float(option.estimated_price)
                ),
                "currency_code": option.currency_code,
                "can_freeze": option.can_freeze,
            }
            for option in package_options
        ],
        "storage_rules": [
            {
                "ingredient_id": rule.ingredient_id,
                "storage_state": rule.storage_state,
                "recommended_storage_location": rule.recommended_storage_location,
                "shelf_life_days": rule.shelf_life_days,
                "freezer_shelf_life_days": rule.freezer_shelf_life_days,
                "storage_instructions": rule.storage_instructions,
            }
            for rule in storage_rules
        ],
    }


def validate_candidates(
    batch: GeneratedRecipeBatch,
    *,
    request: PlanGenerationRequest,
    profile: Any,
    ingredients: Sequence[Any],
    required_meal_types: set[MealType],
) -> list[GeneratedRecipeCandidate]:
    catalog = {ingredient.id: ingredient for ingredient in ingredients}
    excluded = set(request.excluded_ingredient_ids)
    allergies = {str(value) for value in (profile.allergies or [])}
    diets = {str(value).casefold() for value in (profile.dietary_preferences or [])}
    seen_ids: set[str] = set()
    errors: list[str] = []

    for recipe in batch.recipes:
        if recipe.candidate_id in seen_ids:
            errors.append(f"duplicate candidate_id {recipe.candidate_id}")
        seen_ids.add(recipe.candidate_id)
        if request.max_total_minutes is not None:
            if recipe.prep_minutes + recipe.cook_minutes > request.max_total_minutes:
                errors.append(f"{recipe.candidate_id} exceeds the cooking-time limit")
        if not set(recipe.eligible_meal_types).intersection(required_meal_types):
            errors.append(f"{recipe.candidate_id} is not eligible for a requested meal type")

        for item in recipe.ingredients:
            ingredient = catalog.get(item.ingredient_id)
            if ingredient is None:
                errors.append(f"{recipe.candidate_id} uses unknown ingredient {item.ingredient_id}")
                continue
            if item.ingredient_id in excluded:
                errors.append(f"{recipe.candidate_id} uses excluded ingredient {item.ingredient_id}")
            if str(item.unit) != ingredient.base_unit:
                errors.append(
                    f"{recipe.candidate_id} uses {item.unit} instead of {ingredient.base_unit} "
                    f"for ingredient {item.ingredient_id}"
                )
            conflicts = allergies.intersection(ingredient.allergens or [])
            if conflicts:
                errors.append(
                    f"{recipe.candidate_id} conflicts with allergies: {', '.join(sorted(conflicts))}"
                )
            tags = {tag.casefold() for tag in (ingredient.dietary_tags or [])}
            for diet in diets.intersection({"vegan", "vegetarian", "halal", "kosher"}):
                if diet not in tags:
                    errors.append(
                        f"{recipe.candidate_id} contains ingredient {item.ingredient_id} "
                        f"that is not marked {diet}"
                    )

    if errors:
        raise GenerationError("Generated recipes failed validation", details={"violations": errors[:20]})
    return batch.recipes


class OpenAIRecipeGenerator:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    async def generate(
        self,
        *,
        context: dict[str, Any],
        request: PlanGenerationRequest,
        profile: Any,
        ingredients: Sequence[Any],
        required_meal_types: set[MealType],
    ) -> list[GeneratedRecipeCandidate]:
        repair_note: str | None = None
        for attempt in range(2):
            user_content = json.dumps(context, separators=(",", ":"), default=str)
            if repair_note:
                user_content += "\n\nREPAIR THE PREVIOUS RESPONSE. " + repair_note
            try:
                response = await self.client.responses.parse(
                    model=self.model,
                    input=[
                        {"role": "system", "content": SOCIAL_RECIPE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    text_format=GeneratedRecipeBatch,
                    store=False,
                )
                batch = response.output_parsed
                if batch is None:
                    refusal = getattr(response, "output_text", "") or "Model returned no structured output"
                    raise GenerationError(refusal)
                expected_count = int(context.get("candidate_count", len(batch.recipes)))
                if len(batch.recipes) != expected_count:
                    raise GenerationError(
                        f"OpenAI returned {len(batch.recipes)} candidates; expected {expected_count}",
                        details={"expected": expected_count, "received": len(batch.recipes)},
                    )
                return validate_candidates(
                    batch,
                    request=request,
                    profile=profile,
                    ingredients=ingredients,
                    required_meal_types=required_meal_types,
                )
            except GenerationError as exc:
                if attempt == 0:
                    repair_note = json.dumps(exc.details or {"message": exc.message})
                    continue
                raise
            except PydanticValidationError as exc:
                if attempt == 0:
                    repair_note = f"Return valid strict structured output: {exc}"
                    continue
                raise GenerationError("OpenAI returned invalid structured recipe data") from exc
            except Exception as exc:
                # Keep SDK/network details out of the API response while retaining the original traceback.
                raise GenerationUnavailableError(
                    "Recipe generation is temporarily unavailable. Please retry."
                ) from exc
        raise GenerationError("Recipe generation failed after one repair attempt")
