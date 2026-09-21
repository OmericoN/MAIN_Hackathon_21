from src.app.config import Settings
from src.app.database import normalize_database_url


def test_settings_derives_supabase_url_from_pooler_username() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://postgres.abc123:secret@pooler.example.com:5432/postgres",
    )

    assert settings.resolved_supabase_url == "https://abc123.supabase.co"
    assert settings.jwks_url == "https://abc123.supabase.co/auth/v1/.well-known/jwks.json"


def test_database_url_is_normalized_for_asyncpg() -> None:
    url = normalize_database_url("postgresql://user:secret@example.com:5432/postgres?sslmode=require")

    assert url.drivername == "postgresql+asyncpg"
    assert "sslmode" not in url.query
    assert url.render_as_string(hide_password=True).startswith("postgresql+asyncpg://user:")
