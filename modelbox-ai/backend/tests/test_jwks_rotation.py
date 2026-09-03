"""An IdP key rotation does not take the appliance down (G8).

The RS256 path verified against a static PEM in configuration. Every identity
provider rotates its signing key on a schedule, and some do it without
announcement — so a pinned key means that one morning every token fails at once,
on a deployment nobody changed, with an error indistinguishable from an attack.
The operator's remedy was to notice, find the new key, and edit a config file.

That is an outage with a manual runbook, which is not an SSO story, and it is
what these tests exist to prevent.

**Every test here uses real RSA keys and real signatures.** A mocked verifier
would let the interesting cases pass by construction — particularly the one that
matters most, where a token signed by a *retired* key must still be refused.
Two keypairs are generated once for the module: one "old", one "new".
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.core import jwks, security
from app.core.config import get_settings

ISSUER = "https://idp.example.com"
AUDIENCE = "modelbox"
JWKS_URL = "https://idp.example.com/.well-known/jwks.json"


def _keypair(kid: str) -> dict[str, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()

    def b64(value: int) -> str:
        import base64

        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    from cryptography.hazmat.primitives import serialization

    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {
        "kid": kid,
        "pem": pem,
        "jwk": {
            "kty": "RSA",
            "kid": kid,
            "use": "sig",
            "alg": "RS256",
            "n": b64(numbers.n),
            "e": b64(numbers.e),
        },
    }


OLD = _keypair("key-old")
NEW = _keypair("key-new")


def _token(pair: dict[str, Any]) -> str:
    return jwt.encode(
        {"sub": "00u-abc", "iss": ISSUER, "aud": AUDIENCE},
        pair["pem"],
        algorithm="RS256",
        headers={"kid": pair["kid"]},
    )


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture
def idp(monkeypatch: pytest.MonkeyPatch):
    """A configured IdP whose published key set the test controls."""
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_algorithm", "RS256", raising=False)
    monkeypatch.setattr(settings, "jwt_jwks_url", JWKS_URL, raising=False)
    monkeypatch.setattr(settings, "jwt_audience", AUDIENCE, raising=False)
    monkeypatch.setattr(settings, "jwt_issuer", ISSUER, raising=False)
    monkeypatch.setattr(settings, "jwt_public_key", None, raising=False)
    jwks.reset_cache()

    state = {"keys": [OLD["jwk"]], "fetches": 0, "fail": False}

    def _get(url: str, timeout: float = 5.0):
        state["fetches"] += 1
        if state["fail"]:
            raise RuntimeError("idp unreachable")
        return _Response({"keys": state["keys"]})

    monkeypatch.setattr(jwks.httpx, "get", _get)
    return state


def test_a_token_signed_by_the_published_key_verifies(idp) -> None:
    claims = security.decode_access_token(_token(OLD))
    assert claims["sub"] == "00u-abc"
    assert idp["fetches"] == 1


def test_a_rotation_is_picked_up_without_a_restart(idp) -> None:
    """The whole point. A key the cache has never seen *is* a rotation."""
    security.decode_access_token(_token(OLD))  # warm the cache

    idp["keys"] = [OLD["jwk"], NEW["jwk"]]
    jwks._last_attempt = 0.0  # the cooldown has elapsed

    claims = security.decode_access_token(_token(NEW))
    assert claims["sub"] == "00u-abc"
    assert idp["fetches"] == 2, "the unknown kid should have triggered one refetch"


def test_an_unknown_kid_refetches_at_most_once_per_cooldown(idp) -> None:
    """A forged `kid` must not turn this appliance into a request amplifier.

    Without the cooldown, anybody who can reach the API can make it hammer the
    customer's identity provider at request rate — a denial of service pointed
    at the thing every other login depends on.
    """
    security.decode_access_token(_token(OLD))
    before = idp["fetches"]

    forged = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE},
        NEW["pem"],
        algorithm="RS256",
        headers={"kid": "kid-that-does-not-exist"},
    )
    for _ in range(5):
        with pytest.raises(security.TokenError):
            security.decode_access_token(forged)

    assert idp["fetches"] == before, "a forged kid caused repeated refetches"


def test_a_retired_key_stops_verifying_once_it_leaves_the_document(idp) -> None:
    """The discriminating half of rotation, and the one a mock would hide.

    Merging fetched keys keeps tokens already issued under the old key working
    through the rotation window. What must NOT happen is a key surviving in the
    cache forever after the provider withdrew it — so this asserts the cache
    can be reset and the old signature then fails.
    """
    security.decode_access_token(_token(OLD))

    idp["keys"] = [NEW["jwk"]]
    jwks.reset_cache()

    with pytest.raises(security.TokenError):
        security.decode_access_token(_token(OLD))


def test_a_key_withdrawn_from_the_document_still_verifies_until_the_cache_clears(
    idp,
) -> None:
    """Merged, not replaced — and this test exists because a mutant survived.

    Changing `_keys = {**_keys, **fetched}` to `_keys = fetched` passed every
    other test in this file. The merge is a real decision with a real
    consequence: during a rotation a provider *usually* publishes both keys, but
    the overlap window is not guaranteed, and tokens already issued under a key
    that has just left the document must keep working until they expire.
    Replacing would log those users out mid-session, at the exact moment their
    provider was doing something routine.

    Distinct from `test_a_retired_key_stops_verifying_once_it_leaves_the_document`,
    which resets the cache explicitly. Withdrawal alone is tolerated; an explicit
    reset is not.
    """
    security.decode_access_token(_token(OLD))  # OLD is now cached

    idp["keys"] = [NEW["jwk"]]  # the provider withdraws OLD
    jwks._fetched_at = time.monotonic() - 10_000  # force a revalidating fetch

    claims = security.decode_access_token(_token(NEW))
    assert claims["sub"] == "00u-abc", "the new key should verify"

    claims = security.decode_access_token(_token(OLD))
    assert claims["sub"] == "00u-abc", "a just-withdrawn key should still verify"


def test_an_unreachable_idp_does_not_discard_the_keys_we_hold(idp) -> None:
    """A network blip must not become a total authentication outage.

    The keys already cached are still the right keys. Emptying the cache on a
    failed fetch is the tidy-looking implementation and it converts a momentary
    DNS failure into every user being logged out.
    """
    security.decode_access_token(_token(OLD))

    idp["fail"] = True
    jwks._fetched_at = time.monotonic() - 10_000  # force a revalidation attempt

    claims = security.decode_access_token(_token(OLD))
    assert claims["sub"] == "00u-abc"


def test_a_configured_jwks_never_falls_back_to_the_static_key(
    idp, monkeypatch
) -> None:
    """Refuse rather than degrade — the D2 posture.

    Falling back to the PEM would make a rotation *appear* to work while the
    appliance verified against a key the provider had retired, and the failure
    would surface later as tokens that stop working for no visible reason.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_public_key", OLD["pem"], raising=False)
    idp["keys"] = []
    jwks.reset_cache()

    with pytest.raises(security.TokenError) as exc:
        security.decode_access_token(_token(OLD))
    assert "no verification key" in str(exc.value)


def test_a_token_with_no_kid_is_refused(idp) -> None:
    """Selecting "the only key" works right up until the provider publishes two."""
    anonymous = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE}, OLD["pem"], algorithm="RS256"
    )
    with pytest.raises(security.TokenError):
        security.decode_access_token(anonymous)
