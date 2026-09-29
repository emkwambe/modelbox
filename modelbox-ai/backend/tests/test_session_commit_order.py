"""A request's transaction commits, or fails, before its response is sent.

`SessionDep` declares `get_db_session` with `scope="function"`. FastAPI's
default, `"request"`, ends a dependency after the response has been sent, so a
client could act on a success before the commit behind it was visible, and a
commit that failed would follow a success already sent.

Recorded here from the ASGI messages themselves: the order of the session's
commit and the `http.response.start` the client receives.

* On a real route (minting an API key, with the SQLite test database), the
  commit precedes the response.
* When the commit fails, the client receives a 500 and no success first.
* No route in the application gets `get_db_session` at request scope.

Negative controls (Amendment 2): with `SessionDep` put back to FastAPI's
default scope in-process, the response precedes the commit, and a failed
commit follows a 200 the client has already received.

The in-process transport waits for teardown before returning, which is why a
test that only reads the final response cannot see this. The black-box suite
checks the same property against the running appliance (read-your-writes).

No `from __future__ import annotations` here: the tiny app's route annotation
must be the `SessionDep` object itself for FastAPI to read its scope.
"""

from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import dependencies
from app.core.database import get_db_session
from tests._real_auth import bearer, make_user, make_workspace, sqlite_session


class Events(list):
    def response_statuses(self) -> list[int]:
        return [e[1] for e in self if isinstance(e, tuple) and e[0] == "response"]


def _recording(app: Any, events: Events) -> Any:
    """The app, with every http.response.start recorded as it is sent."""

    async def wrapped(scope: dict, receive: Any, send: Any) -> None:
        async def recording_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                events.append(("response", message["status"]))
            await send(message)

        await app(scope, receive, recording_send)

    return wrapped


def _session_override(events: Events, session: Any = None, *, fail: bool = False):
    async def _session() -> AsyncIterator[Any]:
        yield session
        if fail:
            events.append("commit-failed")
            raise RuntimeError("commit failed")
        if session is not None:
            await session.commit()
        events.append("commit")

    return _session


def _tiny_app() -> FastAPI:
    """One route that depends on `dependencies.SessionDep` as it is now."""
    app = FastAPI()
    session_dep = dependencies.SessionDep

    @app.post("/write")
    async def write(session: session_dep) -> dict:  # type: ignore[valid-type]
        return {"ok": True}

    return app


async def _call(app: FastAPI, events: Events, method: str, path: str, **kwargs: Any) -> int:
    transport = ASGITransport(app=_recording(app, events), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        return (await client.request(method, path, **kwargs)).status_code


def _check_commit_precedes_response(events: Events) -> None:
    """The check, shared by the tests and their negative control."""
    assert "commit" in events, f"fixture sanity: no commit recorded: {events}"
    first_response = next(i for i, e in enumerate(events) if isinstance(e, tuple))
    assert events.index("commit") < first_response, (
        f"the response was sent before the commit: {events}"
    )


def _check_failed_commit_sends_no_success(events: Events) -> None:
    """The check, shared by the tests and their negative control."""
    assert "commit-failed" in events, f"fixture sanity: the commit did not fail: {events}"
    statuses = events.response_statuses()
    assert statuses and all(s >= 500 for s in statuses), (
        f"a failed commit sent {statuses}: a success reached the client first"
    )


@pytest.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


async def test_a_real_write_commits_before_its_response(session: AsyncSession) -> None:
    from app.main import create_app

    owner = await make_user(session, "owner@example.com")
    workspace = await make_workspace(session, "A", {owner: "OWNER"})
    await session.commit()
    events = Events()
    app = create_app()
    app.dependency_overrides[get_db_session] = _session_override(events, session)
    status = await _call(
        app, events, "POST", "/api/v1/auth/api-keys",
        headers=bearer(owner), json={"name": "k", "workspace_id": str(workspace.workspace_id)},
    )
    assert status == 201
    _check_commit_precedes_response(events)


async def test_a_failed_commit_is_a_500_and_nothing_else(session: AsyncSession) -> None:
    from app.main import create_app

    owner = await make_user(session, "owner@example.com")
    workspace = await make_workspace(session, "A", {owner: "OWNER"})
    await session.commit()
    events = Events()
    app = create_app()
    app.dependency_overrides[get_db_session] = _session_override(events, session, fail=True)
    status = await _call(
        app, events, "POST", "/api/v1/auth/api-keys",
        headers=bearer(owner), json={"name": "k", "workspace_id": str(workspace.workspace_id)},
    )
    assert status == 500
    _check_failed_commit_sends_no_success(events)


def test_no_route_gets_the_session_at_request_scope() -> None:
    """Every route, through every included router (`test_route_policy._flatten`)."""
    from app.main import create_app
    from tests.test_route_policy import _flatten

    found: list[tuple[str, str | None]] = []

    def walk(dependant: Any, path: str) -> None:
        for sub in dependant.dependencies:
            if sub.call is get_db_session:
                found.append((path, sub.scope))
            walk(sub, path)

    for path, route in _flatten(create_app().routes):
        walk(route.dependant, path)
    assert found, "fixture sanity: no route depends on get_db_session"
    wrong = sorted({path for path, scope in found if scope != "function"})
    assert not wrong, f"routes get the session at request scope: {wrong}"


async def test_the_tiny_app_commits_before_its_response() -> None:
    """Pairs with the negative control below: same app, the scope as shipped."""
    events = Events()
    app = _tiny_app()
    app.dependency_overrides[get_db_session] = _session_override(events)
    assert await _call(app, events, "POST", "/write") == 200
    _check_commit_precedes_response(events)


# --- Negative controls ----------------------------------------------------------


def _request_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies, "SessionDep", Annotated[AsyncSession, Depends(get_db_session)]
    )


async def test_negative_control_request_scope_responds_before_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _request_scoped(monkeypatch)
    events = Events()
    app = _tiny_app()
    app.dependency_overrides[get_db_session] = _session_override(events)
    assert await _call(app, events, "POST", "/write") == 200
    with pytest.raises(AssertionError, match="the response was sent before the commit"):
        _check_commit_precedes_response(events)


async def test_negative_control_request_scope_sends_a_success_before_a_failed_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _request_scoped(monkeypatch)
    events = Events()
    app = _tiny_app()
    app.dependency_overrides[get_db_session] = _session_override(events, fail=True)
    await _call(app, events, "POST", "/write")
    with pytest.raises(AssertionError, match="a success reached the client first"):
        _check_failed_commit_sends_no_success(events)
