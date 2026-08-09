"""Authentication primitives: JWT verification and password hashing.

Supports HS256 for local/test tokens and RS256 for enterprise OIDC identity
providers (verified against a configured public key). Password hashing uses
bcrypt via passlib.
"""

from __future__ import annotations

import datetime
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

# bcrypt operates on the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """Raised when a token cannot be decoded or verified."""


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password``."""
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify ``password`` against a stored bcrypt ``hashed`` value."""
    try:
        return bcrypt.checkpw(_encode(password), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: str, expires_minutes: int | None = None
) -> str:
    """Mint an HS256 access token for ``subject`` (typically a user id).

    Used for local development and tests; enterprise deployments receive tokens
    from their OIDC provider and only the verification path is exercised.
    """
    settings = get_settings()
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, returning its claims.

    HS256 tokens verify against ``jwt_secret``; RS256 tokens verify against the
    configured ``jwt_public_key``. Raises :class:`TokenError` on any failure.
    """
    settings = get_settings()
    algorithm = settings.jwt_algorithm
    key = (
        settings.jwt_public_key
        if algorithm.startswith("RS") and settings.jwt_public_key
        else settings.jwt_secret
    )
    try:
        return jwt.decode(token, key, algorithms=[algorithm])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
