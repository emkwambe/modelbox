"""Production closes self-registration, and create-owner makes the first account.

Owner decision H3 (Sprint 7): `POST /auth/register` is refused when
`ENVIRONMENT=production` unless `MODELBOX_ALLOW_REGISTRATION=true`, and only
together with a bootstrap. With no seeded account, no registration and an
empty OIDC allowlist, a fresh production appliance would otherwise have no way
for anyone to sign in. `python -m app.cli create-owner` is that way, and it
refuses once an owner exists.

Registration is exercised over HTTP with production settings. The only
override is configuration (`get_settings`); who the caller is is never
overridden. The created owner signs in through the real `/auth/token`.

Negative controls patch exactly the functions the fix introduced:
`registration_allowed` and `owner_exists`.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.api.v1.endpoints import auth
from app.core.config import Settings, get_settings
from app.models.metadata_store import User, WorkspaceMember
from tests._real_auth import make_user, make_workspace, real_client, sqlite_session

PASSWORD = "a-long-enough-password"
SECRETS = {
    "jwt_secret": "j" * 48,
    "encryption_key": "e" * 48,
    "database_url": "postgresql+asyncpg://modelbox:" + "p" * 32 + "@db:5432/modelbox_metadata",
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**SECRETS, **overrides})  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    async for s in sqlite_session(monkeypatch):
        yield s


async def _register(session: AsyncSession, config: Settings) -> int:
    async with real_client(session, {get_settings: lambda: config}) as client:
        response = await client.post(
            "/api/v1/auth/register", json={"email": "new@example.com", "password": PASSWORD}
        )
    return response.status_code


async def _users(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(User))).scalar_one()


# --- Registration -----------------------------------------------------------


async def _check_production_refuses(session: AsyncSession) -> None:
    """The check, shared by the test and its negative control."""
    status = await _register(session, _settings(environment="production"))
    assert status == 403, f"production registration returned {status}"
    assert await _users(session) == 0, "a refused registration still created a user"


async def test_production_refuses_self_registration(session) -> None:
    await _check_production_refuses(session)


async def test_production_can_opt_in(session) -> None:
    config = _settings(environment="production", allow_registration=True)
    assert await _register(session, config) == 201


@pytest.mark.parametrize("environment", ["development", "staging"])
async def test_other_environments_keep_registration(session, environment) -> None:
    assert await _register(session, _settings(environment=environment)) == 201


def test_the_flag_reads_its_documented_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELBOX_ALLOW_REGISTRATION", "true")
    assert _settings().allow_registration is True


# --- create-owner -----------------------------------------------------------


async def _check_second_owner_refused(session: AsyncSession) -> None:
    """The check, shared by the test and its negative control."""
    await cli.create_owner(session, "first@example.com", PASSWORD, "Org")
    with pytest.raises(cli.CreateOwnerRefused, match="owner already exists"):
        await cli.create_owner(session, "second@example.com", PASSWORD, "Other")


async def test_create_owner_makes_an_owner_who_can_sign_in(session) -> None:
    await cli.create_owner(session, "owner@example.com", PASSWORD, "Org")
    roles = (await session.execute(select(WorkspaceMember.role))).scalars().all()
    assert roles == ["OWNER"]
    async with real_client(session) as client:
        response = await client.post(
            "/api/v1/auth/token", data={"username": "owner@example.com", "password": PASSWORD}
        )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


async def test_create_owner_refuses_a_second_owner(session) -> None:
    await _check_second_owner_refused(session)
    assert await _users(session) == 1


async def test_create_owner_refuses_when_any_workspace_has_an_owner(session) -> None:
    """Appliance-wide: an owner made any other way also blocks the bootstrap."""
    someone = await make_user(session, "someone@example.com")
    await make_workspace(session, "Theirs", {someone: "OWNER"})
    await session.commit()
    with pytest.raises(cli.CreateOwnerRefused, match="owner already exists"):
        await cli.create_owner(session, "owner@example.com", PASSWORD, "Org")


async def test_create_owner_refuses_a_short_password(session) -> None:
    with pytest.raises(cli.CreateOwnerRefused, match="at least 12"):
        await cli.create_owner(session, "owner@example.com", "short", "Org")
    assert await _users(session) == 0


def test_the_password_is_not_an_argument() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            ["create-owner", "--email", "a@example.com", "--password", PASSWORD]
        )


def test_the_prompt_asks_twice_and_refuses_a_mismatch() -> None:
    answers = iter(["one-password-here", "another-password"])
    with pytest.raises(cli.CreateOwnerRefused, match="did not match"):
        cli.read_password(False, prompt=lambda _: next(answers))


async def test_the_command_reads_stdin_and_never_prints_the_password(
    session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real command, end to end, against this test's database."""
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    code = await cli.run(
        ["create-owner", "--email", "owner@example.com", "--password-stdin"],
        session.info["maker"],
    )
    out = capsys.readouterr()
    assert code == 0, out.err
    assert PASSWORD not in out.out + out.err
    async with real_client(session) as client:
        signed_in = await client.post(
            "/api/v1/auth/token", data={"username": "owner@example.com", "password": PASSWORD}
        )
    assert signed_in.status_code == 200, "the password read from stdin is not the one stored"


async def test_designate_refuses_while_an_appliance_owner_exists(session) -> None:
    await cli.create_owner(session, "owner@example.com", PASSWORD, "Org")
    code = await cli.run(
        ["designate-appliance-owner", "--email", "owner@example.com"], session.info["maker"]
    )
    assert code == 1


async def test_designate_refuses_someone_who_owns_no_workspace(session) -> None:
    user = await make_user(session, "member@example.com")
    await make_workspace(session, "W", {user: "MEMBER"})
    await session.commit()
    code = await cli.run(
        ["designate-appliance-owner", "--email", "member@example.com"], session.info["maker"]
    )
    assert code == 1


# --- Negative controls ------------------------------------------------------


async def test_negative_control_without_the_gate_production_registers(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "registration_allowed", lambda config: True)
    with pytest.raises(AssertionError, match="returned 201"):
        await _check_production_refuses(session)


async def test_negative_control_without_the_owner_check_a_second_owner_is_made(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nobody(_session: AsyncSession) -> bool:
        return False

    monkeypatch.setattr(cli, "owner_exists", nobody)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        await _check_second_owner_refused(session)
