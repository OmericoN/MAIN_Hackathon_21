from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .auth import Principal, get_principal
from .config import Settings, get_settings


def normalize_database_url(value: str) -> URL:
    url = make_url(value)
    query = dict(url.query)
    query.pop("sslmode", None)
    return url.set(drivername="postgresql+asyncpg", query=query)


def build_engine(settings: Settings) -> AsyncEngine:
    url = normalize_database_url(settings.database_url)
    connect_args: dict[str, object] = {
        "ssl": "require",
        "server_settings": {
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "idle_in_transaction_session_timeout": str(settings.db_statement_timeout_ms),
        },
    }
    if url.port == 6543:
        connect_args["statement_cache_size"] = 0
        url = url.update_query_dict({"prepared_statement_cache_size": "0"})

    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args=connect_args,
    )


settings = get_settings()
engine = build_engine(settings)
session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def scope_session_to_principal(session: AsyncSession, principal: Principal) -> None:
    claims_json = json.dumps(principal.claims, separators=(",", ":"), default=str)
    await session.execute(
        text("select set_config('request.jwt.claims', :claims, true)"),
        {"claims": claims_json},
    )
    await session.execute(text("set local role authenticated"))


async def get_user_session(
    principal: Principal = Depends(get_principal),
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        async with session.begin():
            await scope_session_to_principal(session, principal)
            yield session


async def database_is_ready() -> bool:
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text("select 1"))).scalar_one() == 1
    except Exception:
        return False


async def close_database() -> None:
    await engine.dispose()
