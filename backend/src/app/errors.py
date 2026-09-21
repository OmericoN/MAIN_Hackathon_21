from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(DomainError):
    status_code = 401
    code = "unauthorized"


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"


class GenerationUnavailableError(DomainError):
    status_code = 503
    code = "generation_unavailable"


class GenerationError(DomainError):
    status_code = 502
    code = "generation_failed"
