from datetime import UTC, datetime
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from uuid import uuid4

from main import app
from src.app.auth import Principal, get_principal
from src.app.database import get_user_session
from src.app.models import Profile


def test_protected_route_requires_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/me/profile")

    assert response.status_code == 401
    assert response.json() == {
        "code": "unauthorized",
        "message": "Bearer access token required",
        "details": None,
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_openapi_exposes_expected_workflow_routes() -> None:
    schema = app.openapi()

    assert "/v1/me/onboarding" in schema["paths"]
    assert "/v1/receipts/{receipt_id}/confirm" in schema["paths"]
    assert "/v1/meal-plans/{plan_id}/shopping-list/rebuild" in schema["paths"]
    assert "/v1/meal-plan-previews" in schema["paths"]
    assert "/v1/meal-plan-previews/{preview_id}/reoptimize" in schema["paths"]
    assert "/v1/meal-plan-previews/{preview_id}/confirm" in schema["paths"]
    assert "/v1/ingredient-package-options" in schema["paths"]
    assert "/v1/waste-events" in schema["paths"]
    onboarding_fields = schema["components"]["schemas"]["OnboardingPut"]["properties"]
    profile_fields = schema["components"]["schemas"]["ProfileRead"]["properties"]
    assert set(onboarding_fields) == {
        "display_name",
        "dietary_preferences",
        "allergies",
        "preferred_cuisines",
        "preferred_tastes",
        "daily_calorie_target",
    }
    assert "onboarding_completed_at" in profile_fields
    assert "activity_level" not in profile_fields


def test_validation_errors_use_the_shared_error_shape() -> None:
    principal = Principal(uuid4(), {"sub": str(uuid4()), "role": "authenticated"})

    async def fake_principal() -> Principal:
        return principal

    async def fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_principal] = fake_principal
    app.dependency_overrides[get_user_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/pantry-items",
                json={"ingredient_id": 1, "initial_quantity": -1, "unit": "each"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Request validation failed"


def test_onboarding_replaces_preferences_and_preserves_completion_time() -> None:
    user_id = uuid4()
    principal = Principal(user_id, {"sub": str(user_id), "role": "authenticated"})
    now = datetime.now(UTC)
    profile = Profile(
        user_id=user_id,
        display_name=None,
        dietary_preferences=[],
        allergies=[],
        preferred_cuisines=[],
        preferred_tastes=[],
        daily_calorie_target=None,
        onboarding_completed_at=None,
        locale="en-NL",
        timezone="Europe/Amsterdam",
        currency_code="EUR",
        created_at=now,
        updated_at=now,
    )
    session = AsyncMock()
    session.get.return_value = profile

    async def fake_principal() -> Principal:
        return principal

    async def fake_session():
        yield session

    app.dependency_overrides[get_principal] = fake_principal
    app.dependency_overrides[get_user_session] = fake_session
    try:
        with TestClient(app) as client:
            first = client.put(
                "/v1/me/onboarding",
                json={
                    "dietary_preferences": [" Vegetarian "],
                    "allergies": ["milk"],
                    "preferred_cuisines": [" Italian "],
                    "preferred_tastes": [" Umami "],
                    "daily_calorie_target": 2_000,
                },
            )
            completed_at = first.json()["onboarding_completed_at"]
            second = client.put("/v1/me/onboarding", json={})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["preferred_tastes"] == ["umami"]
    assert first.json()["allergies"] == ["milk"]
    assert completed_at is not None
    assert second.status_code == 200
    assert second.json()["dietary_preferences"] == []
    assert second.json()["preferred_tastes"] == []
    assert second.json()["onboarding_completed_at"] == completed_at
