"""Every route declares a minimum role, and its dependency chain enforces it.

`app/api/v1/route_policy.py` is the table. This walks every route the
application serves and fails if a route is missing from the table, if the
table names a route that no longer exists, if a public route is not on the
allowlist, or if a route's dependency chain does not carry the declared role.
It replaces a guard that scanned the source of `models.py` alone.

**The walk recurses.** This FastAPI keeps an included router as one lazy
entry in `app.routes` rather than copying its routes up, so iterating
`app.routes` sees `/health` and nothing else, and a check built that way would
pass having checked one route. The walk follows included routers at any depth;
a precondition asserts it found every route, and the first negative control
hides an unguarded route two routers down to prove it is found there.

The role is read from the dependencies themselves: each enforcing dependency
in `app.api.v1.dependencies` carries `policy_role`, so a check inside a
handler body, invisible to this walk, does not count.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.v1.dependencies import _ROLE_LEVEL, require_model_role
from app.api.v1.endpoints.scim import require_scim_token
from app.api.v1.route_policy import (
    APPLIANCE_OWNER,
    AUTHENTICATED,
    PUBLIC,
    PUBLIC_ALLOWLIST,
    ROUTE_POLICY,
    SCIM,
)
from app.main import create_app

LEVEL = {AUTHENTICATED: 0, **_ROLE_LEVEL, APPLIANCE_OWNER: max(_ROLE_LEVEL.values()) + 1}


def _flatten(routes: list[Any], prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Every APIRoute with its full path, through included routers at any depth."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _flatten(inner.routes, prefix + (route.include_context.prefix or ""))


def _calls(dependant: Dependant) -> Iterator[Any]:
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _served(app: FastAPI) -> dict[tuple[str, str], APIRoute]:
    return {
        (method, path): route
        for path, route in _flatten(app.routes)
        for method in route.methods
    }


def _route_problem(key: tuple[str, str], route: APIRoute, expected: str | None) -> str | None:
    """Why ``route`` does not meet ``expected``, or None if it does."""
    if expected is None:
        return f"{key[0]} {key[1]} is not in the route policy table"
    calls = list(_calls(route.dependant))
    roles = [c.policy_role for c in calls if hasattr(c, "policy_role")]
    if expected == PUBLIC:
        if key not in PUBLIC_ALLOWLIST:
            return f"{key[0]} {key[1]} is PUBLIC but not on the allowlist"
        return None
    if expected == SCIM:
        if require_scim_token not in calls:
            return f"{key[0]} {key[1]} is SCIM but does not require the SCIM token"
        return None
    if not roles:
        return f"{key[0]} {key[1]} declares {expected} but no dependency enforces a role"
    strongest = max(roles, key=lambda role: LEVEL[role])
    if strongest != expected:
        return f"{key[0]} {key[1]} declares {expected} but its chain enforces {strongest}"
    return None


def _check_policy(app: FastAPI, table: dict[tuple[str, str], str]) -> None:
    """The check, shared by the test and its negative controls."""
    served = _served(app)
    problems = [
        problem
        for key, route in sorted(served.items())
        if (problem := _route_problem(key, route, table.get(key)))
    ]
    problems += [
        f"{method} {path} is in the table but not served"
        for method, path in sorted(table)
        if (method, path) not in served
    ]
    assert not problems, "route policy violations:\n" + "\n".join(problems)


def test_the_walk_finds_every_route() -> None:
    """Precondition: 77 routes, reached through included routers (Step 4b
    added the two attestation routes and the four classification routes;
    Step 5 the drift report; Step 6 the four members routes; Sprint 9 Step 3
    the twelve mapping routes; Sprint 9 Step 4 the four suggestion routes)."""
    served = _served(create_app())
    assert len(served) == len(ROUTE_POLICY) == 77
    assert ("POST", "/api/v1/model/{model_id}/transform-paradigm") in served


def test_every_route_enforces_its_declared_role() -> None:
    _check_policy(create_app(), ROUTE_POLICY)


def test_the_allowlist_is_exactly_the_public_routes() -> None:
    public = {key for key, role in ROUTE_POLICY.items() if role == PUBLIC}
    assert public == set(PUBLIC_ALLOWLIST)


def test_every_declared_role_is_a_real_level() -> None:
    """A misspelt role would raise KeyError in the walk rather than fail clearly."""
    for key, role in ROUTE_POLICY.items():
        assert role in {PUBLIC, SCIM, *LEVEL}, f"{key}: unknown role {role!r}"


# --- Negative controls -------------------------------------------------------


def test_negative_control_an_unguarded_route_in_a_nested_router_fails() -> None:
    app = create_app()
    inner = APIRouter(prefix="/inner")

    @inner.get("/leak")
    async def leak() -> dict[str, str]:  # pragma: no cover - never requested
        return {}

    outer = APIRouter(prefix="/zz-outer")
    outer.include_router(inner)
    app.include_router(outer, prefix="/api/v1")

    # Precondition: the walk reaches a route two routers down.
    assert ("GET", "/api/v1/zz-outer/inner/leak") in _served(app)
    with pytest.raises(AssertionError, match="/api/v1/zz-outer/inner/leak is not in"):
        _check_policy(app, ROUTE_POLICY)


# Module level: with postponed annotations, FastAPI resolves a route's
# annotations against the module's globals, so a local would not be found.
_VIEWER_ONLY = require_model_role("VIEWER")


async def _weakened_transform(  # pragma: no cover - never requested
    model: Annotated[Any, Depends(_VIEWER_ONLY)],
) -> None:
    return None


def test_negative_control_a_weakened_transform_guard_fails() -> None:
    """The transform route enforcing only VIEWER, as if its guard were reverted."""
    weakened = FastAPI()
    weakened.post("/api/v1/model/{model_id}/transform-paradigm")(_weakened_transform)
    key = ("POST", "/api/v1/model/{model_id}/transform-paradigm")
    with pytest.raises(AssertionError, match="declares MEMBER but its chain enforces VIEWER"):
        _check_policy(weakened, {key: ROUTE_POLICY[key]})
