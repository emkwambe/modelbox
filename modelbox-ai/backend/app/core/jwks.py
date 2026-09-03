"""Verification keys fetched from an IdP's JWKS, and rotated without downtime (G8).

The RS256 path verified against a **static PEM** in configuration. That works
until the identity provider rotates its signing key, which every provider does
on a schedule and some do without announcement — and then every token fails at
once, on a deployment nobody changed, with an error that looks like a signature
attack. The operator's fix is to notice, find the new key, and edit a config
file. That is an outage with a manual runbook, and it is why a static key is not
an SSO story.

Three rulings, each with a plausible-looking opposite.

**An unknown `kid` triggers exactly one refetch, then fails.** This is the whole
rotation mechanism: a key the cache has never seen is what a rotation looks
like from here. The opposite — refetching on every verification failure — turns
any attacker with a forged header into a request amplifier pointed at the IdP,
so the refetch is gated by a cooldown and a failure after it is simply a
failure.

**The cache is never emptied on a failed fetch.** If the IdP is briefly
unreachable, the keys we already hold are still the right keys, and discarding
them converts a network blip into a total authentication outage. A stale key
that still verifies is strictly better than no key at all.

**No key means refuse, never fall through.** A JWKS URL that is configured and
unreachable must not silently degrade to the static PEM or to an unverified
decode. That is the D2 posture the rest of this codebase already takes: a check
that cannot be performed is loud, never skipped.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Minimum seconds between refetches. Bounds how hard a stream of forged `kid`
#: headers can make this appliance hammer the identity provider.
_REFETCH_COOLDOWN = 30.0

#: How long a successfully fetched set is served without revalidation.
_CACHE_TTL = 3600.0

_keys: dict[str, dict[str, Any]] = {}
_fetched_at: float = 0.0
_last_attempt: float = 0.0


def reset_cache() -> None:
    """Drop the cache. For tests, and for an operator forcing a reload."""
    global _keys, _fetched_at, _last_attempt
    _keys = {}
    _fetched_at = 0.0
    _last_attempt = 0.0


def _fetch(url: str) -> bool:
    """Fetch and merge the key set. Returns whether anything was learned."""
    global _keys, _fetched_at, _last_attempt
    _last_attempt = time.monotonic()
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception:  # noqa: BLE001 - see the module docstring
        # Deliberately broad, and deliberately not re-raised: the keys already
        # held are still the right keys, and a network blip must not become a
        # total authentication outage.
        logger.warning("Could not fetch JWKS from %s; keeping cached keys", url)
        return False

    fetched = {
        key["kid"]: key
        for key in payload.get("keys", [])
        if isinstance(key, dict) and key.get("kid")
    }
    if not fetched:
        logger.warning("JWKS at %s contained no usable keys", url)
        return False

    # Merged rather than replaced. During a rotation a provider publishes the
    # new key alongside the old one, but the window is not guaranteed — tokens
    # already issued under a key withdrawn from the document must keep
    # verifying until they expire.
    _keys = {**_keys, **fetched}
    _fetched_at = time.monotonic()
    return True


def key_for(kid: str | None) -> dict[str, Any] | None:
    """Return the JWK for ``kid``, fetching or refetching if warranted.

    ``None`` means the caller cannot verify and must refuse. It never means
    "carry on without checking".
    """
    settings = get_settings()
    url = getattr(settings, "jwt_jwks_url", None)
    if not url:
        return None
    if not kid:
        # A token with no `kid` cannot be matched against a rotating key set.
        # Selecting "the only key" would work today and break silently the
        # first time the provider published two.
        return None

    now = time.monotonic()
    if not _keys or (now - _fetched_at) > _CACHE_TTL:
        _fetch(url)

    if kid in _keys:
        return _keys[kid]

    # Unknown kid: this is what a rotation looks like. One refetch, cooled down
    # so a stream of forged headers cannot turn this into an amplifier.
    if (now - _last_attempt) >= _REFETCH_COOLDOWN and _fetch(url):
        return _keys.get(kid)

    logger.warning("No verification key for kid %r", kid)
    return None
