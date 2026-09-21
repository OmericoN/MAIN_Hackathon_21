from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.app.database import normalize_database_url


EXPECTED_TABLES = {
    "ingredients",
    "meal_plan_meals",
    "meal_plans",
    "pantry_items",
    "profiles",
    "receipt_items",
    "receipts",
    "recipe_ingredients",
    "recipes",
    "shopping_list_items",
    "shopping_lists",
    "waste_events",
}
EXPECTED_FUNCTIONS = {"confirm_receipt", "rebuild_shopping_list", "record_waste"}
EXPECTED_PROFILE_COLUMNS = {
    "user_id",
    "display_name",
    "dietary_preferences",
    "allergies",
    "preferred_cuisines",
    "preferred_tastes",
    "daily_calorie_target",
    "onboarding_completed_at",
    "locale",
    "timezone",
    "currency_code",
    "created_at",
    "updated_at",
}


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured")
async def test_live_schema_contract_is_present() -> None:
    engine = create_async_engine(normalize_database_url(os.environ["TEST_DATABASE_URL"]), connect_args={"ssl": "require"})
    try:
        async with engine.connect() as connection:
            tables = set(
                (
                    await connection.execute(
                        text("select tablename from pg_tables where schemaname = 'public'")
                    )
                ).scalars()
            )
            functions = set(
                (
                    await connection.execute(
                        text(
                            "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                            "where n.nspname = 'public'"
                        )
                    )
                ).scalars()
            )
            rls_tables = set(
                (
                    await connection.execute(
                        text(
                            "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                            "where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity"
                        )
                    )
                ).scalars()
            )
            profile_columns = set(
                (
                    await connection.execute(
                        text(
                            "select column_name from information_schema.columns "
                            "where table_schema = 'public' and table_name = 'profiles'"
                        )
                    )
                ).scalars()
            )
            profile_policies = (
                await connection.execute(
                    text(
                        "select roles, qual, with_check from pg_policies "
                        "where schemaname = 'public' and tablename = 'profiles'"
                    )
                )
            ).all()
        assert EXPECTED_TABLES <= tables
        assert EXPECTED_FUNCTIONS <= functions
        assert EXPECTED_TABLES <= rls_tables
        assert EXPECTED_PROFILE_COLUMNS <= profile_columns
        assert "activity_level" not in profile_columns
        assert any(
            "authenticated" in roles
            and "auth.uid" in (qual or "")
            and "user_id" in (qual or "")
            and "auth.uid" in (with_check or "")
            and "user_id" in (with_check or "")
            for roles, qual, with_check in profile_policies
        )
    finally:
        await engine.dispose()
