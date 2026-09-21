from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ortools.sat.python import cp_model

from .errors import ConflictError
from .schemas import GeneratedRecipeCandidate, PlanGenerationRequest


SCALE = 1000


def _scaled(value: int | float | Decimal) -> int:
    return int((Decimal(str(value)) * SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _unscaled(value: int) -> float:
    return round(value / SCALE, 3)


def _weight_grams(quantity: int, ingredient: Any) -> int:
    value = _unscaled(quantity)
    if ingredient.base_unit == "g":
        return max(0, round(value))
    if ingredient.base_unit == "ml":
        density = float(ingredient.density_g_per_ml or 1)
        return max(0, round(value * density))
    average_weight = float(ingredient.average_unit_weight_g or 100)
    return max(0, round(value * average_weight))


def _preference_score(candidate: GeneratedRecipeCandidate, request: PlanGenerationRequest, profile: Any) -> int:
    preferred_styles = set(request.preferred_styles)
    preferred_cuisines = set(request.extra_cuisines) | {
        value.casefold() for value in (profile.preferred_cuisines or [])
    }
    preferred_tastes = set(request.extra_tastes) | {
        value.casefold() for value in (profile.preferred_tastes or [])
    }
    score = 10
    score += 12 * len(preferred_styles.intersection(tag.casefold() for tag in candidate.style_tags))
    score += 10 if candidate.cuisine.casefold() in preferred_cuisines else 0
    score += 8 * len(preferred_tastes.intersection(tag.casefold() for tag in candidate.taste_tags))
    if profile.daily_calorie_target and candidate.calories_per_serving:
        per_meal_target = profile.daily_calorie_target / max(1, len(request.meal_types))
        score += max(0, 10 - round(abs(candidate.calories_per_serving - per_meal_target) / 50))
    return max(score, 1)


class WasteFirstOptimizer:
    """Integer CP-SAT selection, lot allocation, and package purchasing model."""

    def solve(
        self,
        *,
        request: PlanGenerationRequest,
        profile: Any,
        meal_slots: list[dict[str, Any]],
        candidates: Sequence[GeneratedRecipeCandidate],
        ingredients: Sequence[Any],
        pantry_items: Sequence[Any],
        package_options: Sequence[Any],
        storage_rules: Sequence[Any],
        pinned_choices: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        pinned_choices = pinned_choices or {}
        catalog = {item.id: item for item in ingredients}
        candidate_by_id = {item.candidate_id: item for item in candidates}
        plan_end = max(slot["meal_date"] for slot in meal_slots)

        overrides = {item.ingredient_id: item for item in request.package_overrides}
        options_by_ingredient: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for option in package_options:
            if option.ingredient_id not in overrides:
                price_matches_currency = (
                    option.estimated_price is not None
                    and option.currency_code == request.currency_code
                )
                options_by_ingredient[option.ingredient_id].append(
                    {
                        "id": option.id,
                        "label": option.label,
                        "quantity": _scaled(option.quantity),
                        "unit": option.unit,
                        "price_cents": (
                            round(float(option.estimated_price) * 100)
                            if price_matches_currency
                            else None
                        ),
                        "currency_code": option.currency_code,
                        "can_freeze": option.can_freeze,
                        "price_source": getattr(
                            option, "price_source", "catalog"
                        ) if price_matches_currency else "unknown",
                    }
                )
        for ingredient_id, override in overrides.items():
            override_price_matches = (
                override.estimated_price is not None
                and override.currency_code == request.currency_code
            )
            options_by_ingredient[ingredient_id] = [
                {
                    "id": None,
                    "label": "User override",
                    "quantity": _scaled(override.quantity),
                    "unit": str(override.unit),
                    "price_cents": (
                        round(float(override.estimated_price) * 100)
                        if override_price_matches
                        else None
                    ),
                    "currency_code": override.currency_code,
                    "can_freeze": override.can_freeze,
                    "price_source": "user_override" if override_price_matches else "unknown",
                }
            ]

        model = cp_model.CpModel()
        eligible: dict[int, list[GeneratedRecipeCandidate]] = {}
        choice: dict[tuple[int, str], cp_model.IntVar] = {}
        use_candidate: dict[str, cp_model.IntVar] = {}
        score_by_candidate = {
            item.candidate_id: _preference_score(item, request, profile) for item in candidates
        }

        for candidate in candidates:
            use_candidate[candidate.candidate_id] = model.new_bool_var(f"use_{candidate.candidate_id}")

        for slot_index, slot in enumerate(meal_slots):
            allowed = [item for item in candidates if slot["meal_type"] in {str(v) for v in item.eligible_meal_types}]
            pinned = pinned_choices.get(slot["slot_key"])
            if pinned:
                allowed = [item for item in allowed if item.candidate_id == pinned]
            if not allowed:
                reason = (
                    f"Pinned recipe {pinned!r} cannot cover {slot['slot_key']}"
                    if pinned
                    else f"No candidate can cover {slot['slot_key']}"
                )
                raise ConflictError("No feasible meal plan", details={"reasons": [reason]})
            eligible[slot_index] = allowed
            vars_for_slot = []
            for candidate in allowed:
                var = model.new_bool_var(f"choose_{slot_index}_{candidate.candidate_id}")
                choice[slot_index, candidate.candidate_id] = var
                vars_for_slot.append(var)
                model.add(var <= use_candidate[candidate.candidate_id])
            model.add_exactly_one(vars_for_slot)

        for candidate_id, used in use_candidate.items():
            candidate_choices = [
                variable for (_, selected_id), variable in choice.items() if selected_id == candidate_id
            ]
            model.add(sum(candidate_choices) >= used)

        # Demand per slot and ingredient is a linear expression driven by the selected recipe.
        demand: dict[tuple[int, int], Any] = {}
        max_demand: dict[tuple[int, int], int] = {}
        ingredient_ids: set[int] = set()
        for slot_index, allowed in eligible.items():
            by_candidate = {
                candidate.candidate_id: {item.ingredient_id: item for item in candidate.ingredients if not item.optional}
                for candidate in allowed
            }
            for ingredient_id in {iid for values in by_candidate.values() for iid in values}:
                terms = []
                maximum = 0
                for candidate in allowed:
                    item = by_candidate[candidate.candidate_id].get(ingredient_id)
                    amount = 0
                    if item:
                        amount = _scaled(item.quantity * request.household_servings / candidate.servings)
                    maximum = max(maximum, amount)
                    terms.append(amount * choice[slot_index, candidate.candidate_id])
                demand[slot_index, ingredient_id] = sum(terms)
                max_demand[slot_index, ingredient_id] = maximum
                ingredient_ids.add(ingredient_id)

        pantry_use: dict[tuple[int, int], cp_model.IntVar] = {}
        pantry_capacity: dict[int, int] = {}
        pantry_by_id = {item.id: item for item in pantry_items}
        for lot in pantry_items:
            capacity = _scaled(lot.remaining_quantity)
            pantry_capacity[lot.id] = capacity
            lot_vars = []
            for slot_index, slot in enumerate(meal_slots):
                if (slot_index, lot.ingredient_id) not in demand:
                    continue
                if lot.best_before_on and slot["meal_date"] > lot.best_before_on:
                    continue
                var = model.new_int_var(0, min(capacity, max_demand[slot_index, lot.ingredient_id]), f"lot_{lot.id}_{slot_index}")
                pantry_use[lot.id, slot_index] = var
                lot_vars.append(var)
            model.add(sum(lot_vars) <= capacity)

        purchased_use: dict[tuple[int, int], cp_model.IntVar] = {}
        package_count: dict[tuple[int, int], cp_model.IntVar] = {}
        package_selected: dict[tuple[int, int], cp_model.IntVar] = {}
        total_required_upper: dict[int, int] = defaultdict(int)
        for (slot_index, ingredient_id), maximum in max_demand.items():
            total_required_upper[ingredient_id] += maximum
            purchased_use[slot_index, ingredient_id] = model.new_int_var(
                0, maximum, f"buy_use_{ingredient_id}_{slot_index}"
            )

        if not request.allow_package_splitting:
            for ingredient_id in ingredient_ids:
                slot_presence = []
                for (slot_index, iid), variable in purchased_use.items():
                    if iid != ingredient_id:
                        continue
                    present = model.new_bool_var(f"purchase_used_{ingredient_id}_{slot_index}")
                    model.add(variable > 0).only_enforce_if(present)
                    model.add(variable == 0).only_enforce_if(present.Not())
                    slot_presence.append(present)
                model.add(sum(slot_presence) <= 1)

        missing_package_options: list[int] = []
        for ingredient_id in ingredient_ids:
            options = [item for item in options_by_ingredient.get(ingredient_id, []) if item["unit"] == catalog[ingredient_id].base_unit]
            pantry_total = sum(
                pantry_capacity[item.id] for item in pantry_items if item.ingredient_id == ingredient_id
            )
            if not options and pantry_total < total_required_upper[ingredient_id]:
                missing_package_options.append(ingredient_id)
                continue
            option_presence = []
            for option_index, option in enumerate(options):
                upper = max(1, (total_required_upper[ingredient_id] + option["quantity"] - 1) // option["quantity"])
                count = model.new_int_var(0, upper, f"packages_{ingredient_id}_{option_index}")
                selected = model.new_bool_var(f"package_selected_{ingredient_id}_{option_index}")
                package_count[ingredient_id, option_index] = count
                package_selected[ingredient_id, option_index] = selected
                model.add(count > 0).only_enforce_if(selected)
                model.add(count == 0).only_enforce_if(selected.Not())
                option_presence.append(selected)
            if option_presence:
                model.add(sum(option_presence) <= 1)

        if missing_package_options:
            names = [catalog[item].name for item in sorted(missing_package_options)]
            raise ConflictError(
                "No feasible meal plan",
                details={"reasons": [f"No package size is configured for: {', '.join(names)}"]},
            )

        # Every selected quantity is covered by an eligible pantry lot or a purchased package.
        for (slot_index, ingredient_id), expression in demand.items():
            lots = [
                variable
                for (lot_id, candidate_slot), variable in pantry_use.items()
                if candidate_slot == slot_index and pantry_by_id[lot_id].ingredient_id == ingredient_id
            ]
            model.add(sum(lots) + purchased_use[slot_index, ingredient_id] == expression)

        for ingredient_id in ingredient_ids:
            purchased = sum(
                variable for (slot_index, iid), variable in purchased_use.items() if iid == ingredient_id
            )
            available_packages = options_by_ingredient.get(ingredient_id, [])
            package_supply = sum(
                option["quantity"] * package_count[ingredient_id, option_index]
                for option_index, option in enumerate(available_packages)
                if (ingredient_id, option_index) in package_count
            )
            model.add(purchased <= package_supply)

        # Primary objective: estimated grams of food likely to expire unused.
        waste_terms: list[Any] = []
        for lot in pantry_items:
            if lot.best_before_on and lot.best_before_on <= plan_end:
                used = sum(variable for (lot_id, _), variable in pantry_use.items() if lot_id == lot.id)
                grams_per_scaled_unit = _weight_grams(SCALE, catalog[lot.ingredient_id])
                waste_terms.append(grams_per_scaled_unit * (pantry_capacity[lot.id] - used))

        freeze_actions: dict[tuple[int, int], cp_model.IntVar] = {}
        freezer_ids = {
            rule.ingredient_id
            for rule in storage_rules
            if rule.freezer_shelf_life_days is not None and rule.freezer_shelf_life_days > 0
        }
        purchased_remainder: dict[int, cp_model.IntVar] = {}
        for ingredient_id in ingredient_ids:
            options = options_by_ingredient.get(ingredient_id, [])
            supply = sum(
                option["quantity"] * package_count[ingredient_id, option_index]
                for option_index, option in enumerate(options)
                if (ingredient_id, option_index) in package_count
            )
            used = sum(variable for (_, iid), variable in purchased_use.items() if iid == ingredient_id)
            upper = max(total_required_upper[ingredient_id], max((item["quantity"] for item in options), default=0))
            remainder = model.new_int_var(0, max(upper, 1), f"remainder_{ingredient_id}")
            purchased_remainder[ingredient_id] = remainder
            model.add(remainder == supply - used)
            ingredient = catalog[ingredient_id]
            if ingredient.typical_shelf_life_days is not None and ingredient.typical_shelf_life_days <= 14:
                for option_index, option in enumerate(options):
                    if option["can_freeze"] and ingredient_id in freezer_ids:
                        frozen = model.new_bool_var(f"freeze_{ingredient_id}_{option_index}")
                        freeze_actions[ingredient_id, option_index] = frozen
                        model.add(frozen <= package_selected[ingredient_id, option_index])
                        # Freezing is an explicit safe action and removes purchased remainder from waste.
                        unfrozen_remainder = model.new_int_var(0, max(upper, 1), f"unfrozen_{ingredient_id}_{option_index}")
                        model.add(unfrozen_remainder == 0).only_enforce_if(frozen)
                        model.add(unfrozen_remainder == remainder).only_enforce_if(frozen.Not())
                        grams_per_scaled_unit = _weight_grams(SCALE, ingredient)
                        waste_terms.append(grams_per_scaled_unit * unfrozen_remainder)
                        break
                else:
                    waste_terms.append(_weight_grams(SCALE, ingredient) * remainder)

        waste_objective = sum(waste_terms)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10
        solver.parameters.num_search_workers = 8
        model.minimize(waste_objective)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ConflictError(
                "No feasible meal plan",
                details={"reasons": self._infeasibility_reasons(request, meal_slots, pinned_choices)},
            )
        best_waste = round(solver.objective_value)
        model.add(waste_objective <= best_waste)

        satisfaction = sum(
            score_by_candidate[candidate_id] * variable
            for (_, candidate_id), variable in choice.items()
        ) + 3 * sum(use_candidate.values())
        model.maximize(satisfaction)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ConflictError("No feasible meal plan after waste minimization")
        best_satisfaction = round(solver.objective_value)
        model.add(satisfaction >= best_satisfaction)

        cost_terms = []
        unknown_price_selected: list[cp_model.IntVar] = []
        for ingredient_id, options in options_by_ingredient.items():
            for option_index, option in enumerate(options):
                key = ingredient_id, option_index
                if key not in package_count:
                    continue
                if option["price_cents"] is None:
                    unknown_price_selected.append(package_selected[key])
                else:
                    cost_terms.append(option["price_cents"] * package_count[key])
        total_cost = sum(cost_terms)
        if request.checkout_budget is not None:
            model.add(total_cost <= round(float(request.checkout_budget) * 100))
        distinct_cooking = sum(use_candidate.values())
        model.minimize(total_cost)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ConflictError(
                "No feasible meal plan",
                details={"reasons": ["The fully priced package total exceeds the checkout budget."]},
            )
        best_cost = round(solver.objective_value)
        model.add(total_cost <= best_cost)
        model.minimize(distinct_cooking)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ConflictError("No feasible meal plan after purchase-cost minimization")
        best_cooking = round(solver.objective_value)
        model.add(distinct_cooking <= best_cooking)

        # FIFO is a final tie-breaker: among otherwise identical plans, consume earlier lots first.
        shelf_penalty = 0
        for lot in pantry_items:
            if lot.best_before_on:
                used = sum(variable for (lot_id, _), variable in pantry_use.items() if lot_id == lot.id)
                days = max(0, (lot.best_before_on - request.start_date).days)
                urgency = max(1, (plan_end - request.start_date).days + 2 - days)
                shelf_penalty += urgency * (pantry_capacity[lot.id] - used)
        model.minimize(shelf_penalty)
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise ConflictError("No feasible meal plan after shelf-life ordering")

        assignments = self._assignments(
            solver, request, meal_slots, eligible, choice, score_by_candidate, candidate_by_id
        )
        shopping = []
        selected_unknown = False
        total_price_cents = 0
        pantry_used_by_ingredient: dict[int, int] = defaultdict(int)
        for (lot_id, _), variable in pantry_use.items():
            pantry_used_by_ingredient[pantry_by_id[lot_id].ingredient_id] += solver.value(variable)
        required_by_ingredient: dict[int, int] = defaultdict(int)
        for slot_index, assignment in enumerate(assignments):
            candidate = candidate_by_id[assignment["candidate_id"]]
            for item in candidate.ingredients:
                if not item.optional:
                    required_by_ingredient[item.ingredient_id] += _scaled(
                        item.quantity * request.household_servings / candidate.servings
                    )

        for ingredient_id, options in options_by_ingredient.items():
            selected_option_index = next(
                (
                    index
                    for index, _ in enumerate(options)
                    if (ingredient_id, index) in package_count
                    and solver.value(package_count[ingredient_id, index]) > 0
                ),
                None,
            )
            if selected_option_index is None:
                continue
            option = options[selected_option_index]
            count = solver.value(package_count[ingredient_id, selected_option_index])
            remainder = solver.value(purchased_remainder[ingredient_id])
            storage_action = None
            freeze = freeze_actions.get((ingredient_id, selected_option_index))
            if freeze is not None and solver.value(freeze):
                storage_action = f"Freeze {_unscaled(remainder)} {catalog[ingredient_id].base_unit} promptly"
            price = None
            if option["price_cents"] is None:
                selected_unknown = True
            else:
                price_cents = option["price_cents"] * count
                total_price_cents += price_cents
                price = round(price_cents / 100, 2)
            shopping.append(
                {
                    "ingredient_id": ingredient_id,
                    "ingredient_name": catalog[ingredient_id].name,
                    "required_quantity": _unscaled(required_by_ingredient[ingredient_id]),
                    "pantry_quantity": _unscaled(pantry_used_by_ingredient[ingredient_id]),
                    "to_buy_quantity": _unscaled(option["quantity"] * count),
                    "unit": catalog[ingredient_id].base_unit,
                    "package_label": option["label"],
                    "package_quantity": _unscaled(option["quantity"]),
                    "package_count": count,
                    "estimated_price": price,
                    "price_source": option["price_source"],
                    "projected_remainder_quantity": _unscaled(remainder),
                    "storage_action": storage_action,
                }
            )

        price_complete = not selected_unknown
        confirmation_blockers = []
        if request.checkout_budget is not None and not price_complete:
            confirmation_blockers.append("Add price overrides for every unpriced shopping package.")
        return {
            "assignments": assignments,
            "shopping": shopping,
            "metrics": {
                "projected_waste_g": best_waste // SCALE,
                "satisfaction_score": solver.value(satisfaction),
                "estimated_purchase_cost": round(total_price_cents / 100, 2) if price_complete else None,
                "currency_code": request.currency_code,
                "price_complete": price_complete,
                "figures_are_estimates": True,
            },
            "confirmation_blocked": bool(confirmation_blockers),
            "confirmation_blockers": confirmation_blockers,
            "objective_order": ["waste", "satisfaction_and_variety", "purchase_cost", "repeated_cooking"],
        }

    @staticmethod
    def _assignments(
        solver: cp_model.CpSolver,
        request: PlanGenerationRequest,
        meal_slots: list[dict[str, Any]],
        eligible: dict[int, list[GeneratedRecipeCandidate]],
        choice: dict[tuple[int, str], cp_model.IntVar],
        scores: dict[str, int],
        candidate_by_id: dict[str, GeneratedRecipeCandidate],
    ) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        fresh_sources: dict[str, list[int]] = defaultdict(list)
        for slot_index, slot in enumerate(meal_slots):
            selected = next(
                candidate
                for candidate in eligible[slot_index]
                if solver.value(choice[slot_index, candidate.candidate_id])
            )
            mode = "fresh"
            source_slot_key = None
            prepared_servings = request.household_servings
            if request.allow_leftovers:
                prior_indices = fresh_sources[selected.candidate_id]
                for prior_index in reversed(prior_indices):
                    days = (slot["meal_date"] - meal_slots[prior_index]["meal_date"]).days
                    group_size = 1 + sum(
                        1
                        for item in assignments
                        if item.get("source_slot_key") == meal_slots[prior_index]["slot_key"]
                    )
                    if 0 < days <= 3 and group_size < request.max_batch_portions:
                        mode = "leftover"
                        source_slot_key = meal_slots[prior_index]["slot_key"]
                        assignments[prior_index]["prepared_servings"] += request.household_servings
                        break
            if mode == "fresh":
                fresh_sources[selected.candidate_id].append(slot_index)
            alternatives = sorted(
                (candidate for candidate in eligible[slot_index] if candidate.candidate_id != selected.candidate_id),
                key=lambda item: (-scores[item.candidate_id], item.title),
            )[:3]
            assignments.append(
                {
                    **slot,
                    "meal_date": slot["meal_date"].isoformat(),
                    "candidate_id": selected.candidate_id,
                    "preparation_mode": mode,
                    "source_slot_key": source_slot_key,
                    "prepared_servings": prepared_servings,
                    "consumed_servings": request.household_servings,
                    "alternative_candidate_ids": [item.candidate_id for item in alternatives],
                }
            )
        return assignments

    @staticmethod
    def _infeasibility_reasons(
        request: PlanGenerationRequest,
        meal_slots: list[dict[str, Any]],
        pinned_choices: dict[str, str],
    ) -> list[str]:
        reasons = []
        if pinned_choices:
            reasons.append("One or more pinned recipe swaps conflict with pantry, package, or budget constraints.")
        if request.checkout_budget is not None:
            reasons.append("The checkout budget may be below the minimum available package cost.")
        if request.max_total_minutes is not None:
            reasons.append("The cooking-time limit leaves too few valid candidates.")
        if not reasons:
            reasons.append(f"Available pantry lots and package sizes cannot cover all {len(meal_slots)} meal slots.")
        return reasons
