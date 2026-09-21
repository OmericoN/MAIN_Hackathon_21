from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

from .api import router
from .config import get_settings
from .database import close_database, database_is_ready
from .errors import DomainError
from .schemas import HealthResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_database()


def _error(code: str, message: str, details=None) -> dict:
    return {"code": code, "message": message, "details": details}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Food Waste API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_error(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder(
                _error("validation_error", "Request validation failed", exc.errors())
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate == "23505":
            message = "A record with these values already exists"
        elif sqlstate == "23503":
            message = "The requested operation conflicts with a related record"
        elif sqlstate == "23514":
            message = "The supplied values violate a data constraint"
        else:
            message = "The database rejected the requested operation"
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error("database_conflict", message),
        )

    @app.exception_handler(DBAPIError)
    async def database_error_handler(_: Request, exc: DBAPIError) -> JSONResponse:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        status_code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if sqlstate in {"P0001", "22000", "22023"}
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            status_code=status_code,
            content=_error("database_rejected", "The database rejected the requested operation"),
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse | JSONResponse:
        ready = await database_is_ready()
        payload = HealthResponse(status="ok" if ready else "degraded", database="up" if ready else "down")
        if ready:
            return payload
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload.model_dump())

    app.include_router(router)
    return app
