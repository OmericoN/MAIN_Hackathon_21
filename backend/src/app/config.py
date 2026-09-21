from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str
    supabase_url: str | None = None
    test_database_url: str | None = None
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    db_statement_timeout_ms: int = Field(default=30_000, ge=1_000)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        if not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError("DATABASE_URL must include a host and database name")
        return value

    @computed_field
    @property
    def resolved_supabase_url(self) -> str:
        if self.supabase_url:
            return self.supabase_url.rstrip("/")

        parsed = urlparse(self.database_url)
        username = unquote(parsed.username or "")
        if "." in username:
            project_ref = username.rsplit(".", 1)[1]
            return f"https://{project_ref}.supabase.co"
        host = parsed.hostname or ""
        if host.startswith("db.") and host.endswith(".supabase.co"):
            return f"https://{host[3:]}"
        raise ValueError("SUPABASE_URL is required when it cannot be derived from DATABASE_URL")

    @property
    def jwt_issuer(self) -> str:
        return f"{self.resolved_supabase_url}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
