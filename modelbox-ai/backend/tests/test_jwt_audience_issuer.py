"""D9 — a signature is not an authorisation.

`decode_access_token` verified the signature and nothing else. That is a real
gap rather than a theoretical one, and the reason is worth stating precisely:
an identity provider signing tokens for a dozen applications signs them all
with the same key. A token minted for a different application by the same IdP
therefore verifies here perfectly. The signature check is not failing — it is
answering "did a key holder mint this", when the question that matters is "was
this minted for *us*".

`aud` answers the second question and `iss` answers "by whom", which is what
makes federation safe. Neither was read.
"""

from __future__ import annotations

import datetime

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.core.security import TokenError, create_access_token, decode_access_token


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch):
    """Configure the service to expect one specific audience and issuer."""
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_AUDIENCE", "modelbox-api")
    monkeypatch.setenv("JWT_ISSUER", "https://idp.example.com/")
    yield get_settings()
    get_settings.cache_clear()


def _mint(settings, *, aud: str | None, iss: str | None) -> str:
    """Mint a correctly *signed* token with arbitrary aud/iss.

    Signed with the service's own secret deliberately. A token an attacker
    forged would fail on the signature and prove nothing about D9; the whole
    point is a token that is cryptographically beyond reproach and still must
    not be accepted.
    """
    claims: dict[str, object] = {
        "sub": "attacker",
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=5),
    }
    if aud is not None:
        claims["aud"] = aud
    if iss is not None:
        claims["iss"] = iss
    return pyjwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def test_token_minted_for_another_audience_is_rejected(pinned) -> None:
    """The register's own wording for D9, asserted directly."""
    token = _mint(pinned, aud="some-other-app", iss="https://idp.example.com/")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_token_from_another_issuer_is_rejected(pinned) -> None:
    token = _mint(pinned, aud="modelbox-api", iss="https://evil.example.com/")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_token_with_no_audience_claim_is_rejected(pinned) -> None:
    """Absence must not read as satisfaction.

    The failure mode a naive implementation has: it compares `claims.get("aud")`
    against the expected value only when the claim is present, so a token
    carrying no audience at all sails through the check that exists to stop it.
    """
    token = _mint(pinned, aud=None, iss="https://idp.example.com/")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_correctly_addressed_token_is_accepted(pinned) -> None:
    """The discriminating half: pinning must not reject the right token.

    Without this, an implementation that refuses everything passes all three
    tests above.
    """
    claims = decode_access_token(create_access_token("user-1"))
    assert claims["sub"] == "user-1"
    assert claims["aud"] == "modelbox-api"
    assert claims["iss"] == "https://idp.example.com/"


def test_unpinned_deployment_still_accepts_its_own_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HS256 with nothing configured keeps working, and mints no claims.

    Local and test tokens are minted by this service against its own secret, so
    the audience question does not arise. Pinning is opt-in there.
    """
    get_settings.cache_clear()
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("JWT_ISSUER", raising=False)
    try:
        claims = decode_access_token(create_access_token("user-2"))
        assert claims["sub"] == "user-2"
        assert "aud" not in claims
    finally:
        get_settings.cache_clear()


def test_rs256_without_pinning_is_refused_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case the opt-in default would otherwise leave wide open.

    RS256 means the tokens come from an external provider — exactly the
    deployment where an unpinned audience is exploitable, and exactly the one
    least likely to notice. Same posture as MODELBOX_FIDELITY_STRICT and
    governance flag D2: a check that cannot be performed must be loud, never
    quietly skipped.
    """
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.delenv("JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("JWT_ISSUER", raising=False)
    try:
        with pytest.raises(TokenError) as exc:
            decode_access_token("any.token.value")
        assert "jwt_audience" in str(exc.value)
        assert "jwt_issuer" in str(exc.value)
    finally:
        get_settings.cache_clear()
