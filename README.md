# Food Waste Meal Planner

This repository contains a Vite/React frontend and a FastAPI backend backed by Supabase Postgres.

## Backend setup

1. Copy `.env.example` to `.env` and fill in the Supabase database URL and project URL.
2. From `backend`, run `uv sync --group dev`.
3. Start the API with `uv run uvicorn main:app --reload`.
4. Open `http://127.0.0.1:8000/docs` for the generated API documentation.

The API verifies Supabase access tokens locally against the project's JWKS endpoint. User-owned database requests execute as the PostgreSQL `authenticated` role with verified JWT claims scoped to the current transaction, so the existing Supabase RLS policies remain active.

The backend does not create or migrate tables. The existing Supabase schema, triggers, grants, and the `confirm_receipt`, `rebuild_shopping_list`, and `record_waste` functions remain authoritative.

Supabase Auth owns account signup. After obtaining an access token, a client can
complete the minimal personalization flow with `PUT /v1/me/onboarding`. The
endpoint stores dietary restrictions, standard allergen codes, preferred
cuisines and tastes, and an optional daily calorie target. `GET` and `PATCH`
`/v1/me/profile` expose the saved profile for later edits.

## Tests

Run `uv run pytest` from `backend`. Unit and API contract tests do not alter the database. Set `TEST_DATABASE_URL` only to a dedicated test database to enable the opt-in read-only schema contract test.
