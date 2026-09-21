from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from src.app.auth import JWTVerifier
from src.app.config import Settings
from src.app.errors import UnauthorizedError


class StubJWKClient:
    def __init__(self, public_key, algorithm: str = "RS256") -> None:
        self.public_key = public_key
        self.algorithm = algorithm

    def get_signing_key_from_jwt(self, _: str):
        return SimpleNamespace(algorithm_name=self.algorithm, key=self.public_key)


def verifier_and_key() -> tuple[JWTVerifier, object]:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://postgres.project:secret@pooler.example.com:5432/postgres",
        supabase_url="https://project.supabase.co",
    )
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = JWTVerifier(settings)
    verifier._jwks = StubJWKClient(private_key.public_key())  # type: ignore[assignment]
    return verifier, private_key


@pytest.mark.asyncio
async def test_verifies_authenticated_supabase_token() -> None:
    verifier, private_key = verifier_and_key()
    user_id = uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
    )

    principal = await verifier.verify(token)

    assert principal.user_id == user_id
    assert principal.claims["role"] == "authenticated"


@pytest.mark.asyncio
async def test_verifies_es256_used_by_the_configured_supabase_project() -> None:
    verifier, _ = verifier_and_key()
    private_key = ec.generate_private_key(ec.SECP256R1())
    verifier._jwks = StubJWKClient(private_key.public_key(), "ES256")  # type: ignore[assignment]
    user_id = uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="ES256",
    )

    assert (await verifier.verify(token)).user_id == user_id


@pytest.mark.asyncio
async def test_rejects_non_authenticated_role() -> None:
    verifier, private_key = verifier_and_key()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "service_role",
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
    )

    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)


@pytest.mark.asyncio
async def test_rejects_expired_token() -> None:
    verifier, private_key = verifier_and_key()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        private_key,
        algorithm="RS256",
    )

    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)
