from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from .config import Settings, get_settings
from .errors import UnauthorizedError


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    claims: dict[str, Any]


class JWTVerifier:
    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.jwt_issuer
        self._jwks = PyJWKClient(
            settings.jwks_url,
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=600,
        )

    async def verify(self, token: str) -> Principal:
        try:
            signing_key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            algorithm = signing_key.algorithm_name
            if algorithm not in {"RS256", "ES256", "EdDSA"}:
                raise UnauthorizedError("Unsupported access-token signing algorithm")
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=self._issuer,
                options={"require": ["exp", "sub", "role"]},
            )
            if claims.get("role") != "authenticated":
                raise UnauthorizedError("An authenticated Supabase user is required")
            return Principal(user_id=UUID(str(claims["sub"])), claims=dict(claims))
        except UnauthorizedError:
            raise
        except (PyJWTError, ValueError, KeyError) as exc:
            raise UnauthorizedError("Invalid or expired access token") from exc


_verifier: JWTVerifier | None = None


def get_jwt_verifier(settings: Settings = Depends(get_settings)) -> JWTVerifier:
    global _verifier
    if _verifier is None:
        _verifier = JWTVerifier(settings)
    return _verifier


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: JWTVerifier = Depends(get_jwt_verifier),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Bearer access token required")
    return await verifier.verify(credentials.credentials)
