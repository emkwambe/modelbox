"""Authentication primitives: JWT verification and password hashing.

Supports HS256 for local/test tokens and RS256 for enterprise OIDC identity
providers (verified against a configured public key). Password hashing uses
bcrypt via passlib.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

# bcrypt operates on the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72

# Programmatic API-key prefix (mb_live_<random>).
_API_KEY_PREFIX = "mb_live_"


def generate_api_key() -> tuple[str, str, str]:
    """Mint a new API key. Returns ``(plaintext, key_prefix, key_hash)``.

    Only the prefix (for display) and the SHA-256 hash (for lookup) are stored;
    the plaintext is returned to the caller once and never persisted.
    """
    key = f"{_API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return key, key[:12], hash_api_key(key)


def hash_api_key(key: str) -> str:
    """Return the SHA-256 hex digest used to look up a stored API key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


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
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, returning its claims.

    HS256 tokens verify against ``jwt_secret``; RS256 tokens verify against the
    configured ``jwt_public_key``. Raises :class:`TokenError` on any failure.

    **Audience and issuer are verified, and under RS256 they are mandatory
    (D9).** A valid signature proves the token came from a key holder. It does
    not prove the token was minted for *this* service. An identity provider
    signing for a dozen applications signs them all with one key, so a token
    issued to any other tenant of that IdP verifies here perfectly — the
    signature check is doing exactly its job and answering a different
    question.

    RS256 means the tokens come from an external provider, which is precisely
    the case where the gap is exploitable, so an RS256 deployment that has not
    pinned both claims is refused rather than served. That is the same posture
    as ``MODELBOX_FIDELITY_STRICT`` and as governance flag D2: a check that
    cannot be performed must be loud, never silently skipped. Under HS256 —
    local and test tokens, minted by this service against its own secret — the
    claims are verified when configured and absent when not.
    """
    settings = get_settings()
    algorithm = settings.jwt_algorithm
    key = (
        settings.jwt_public_key
        if algorithm.startswith("RS") and settings.jwt_public_key
        else settings.jwt_secret
    )
    if algorithm.startswith("RS") and not (
        settings.jwt_audience and settings.jwt_issuer
    ):
        missing = [
            name
            for name, value in (
                ("jwt_audience", settings.jwt_audience),
                ("jwt_issuer", settings.jwt_issuer),
            )
            if not value
        ]
        raise TokenError(
            f"{algorithm} verification requires {' and '.join(missing)}. "
            f"Without them any token this provider signed for any other "
            f"application is accepted here."
        )

    options = {
        "verify_aud": settings.jwt_audience is not None,
        # python-jose does not gate issuer behind an option; passing None
        # skips the check, so the flag lives in the argument itself.
    }
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=options,
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    # Presence is checked separately because the library treats a MISSING
    # claim as nothing to compare rather than as a failure. A token carrying no
    # `aud` at all therefore passes the audience check outright — absence
    # reading as satisfaction, which is the failure mode the check exists to
    # prevent. Caught by a test, not by reading the docs.
    for claim, expected in (
        ("aud", settings.jwt_audience),
        ("iss", settings.jwt_issuer),
    ):
        if expected and claim not in claims:
            raise TokenError(
                f"token carries no {claim!r} claim, but this deployment pins "
                f"{claim} to {expected!r}"
            )
    return claims
