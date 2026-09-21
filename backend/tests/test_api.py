from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from uuid import uuid4

from main import app
from src.app.auth import Principal, get_principal
from src.app.database import get_user_session


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

    assert "/v1/receipts/{receipt_id}/confirm" in schema["paths"]
    assert "/v1/meal-plans/{plan_id}/shopping-list/rebuild" in schema["paths"]
    assert "/v1/waste-events" in schema["paths"]


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
