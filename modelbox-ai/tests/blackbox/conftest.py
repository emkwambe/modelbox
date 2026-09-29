"""The black-box harness: the running appliance, driven from outside.

Nothing here imports the application. The suite talks to the appliance the way
an operator or a user would: HTTP through the one published port (the UI,
which forwards /api/* to the backend), `docker compose exec` for the operator
CLI, and `psql` inside the database container. The stack is started and
stopped by the CI job; the suite only uses it.

**Profiles** (``BLACKBOX_PROFILE``):

* ``hardened``: docker/docker-compose.appliance.yml with a `.env` from
  init-env. Every check must pass.
* ``insecure``: the same plus tests/blackbox/compose/insecure.yml, which puts
  back weaknesses by configuration (Amendment 3). A check marked
  ``weakened_by_insecure`` must fail there, and fail on its own check.
* ``egress-deny``: configuration C, plus tests/blackbox/compose/egress-deny.yml.

**How "must fail" is asserted.** A check raises :class:`CheckFailed`, and
nothing else does. Under the insecure profile each ``weakened_by_insecure``
test becomes ``xfail(raises=CheckFailed, strict=True)``: passing is an error
(the check cannot see the weakness), and so is failing any other way (a setup
error is not the check failing). Every other test must pass under every
profile, so the insecure profile weakens only what it says it does.

Secrets are read from `.env` and passed to subprocesses through their
environment, never on a command line and never in a message.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import bcrypt
import httpx
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # modelbox-ai/
BASE_COMPOSE = ROOT / "docker" / "docker-compose.appliance.yml"
ENV_FILE = ROOT / ".env"

PROFILE = os.environ.get("BLACKBOX_PROFILE", "hardened")
_OVERRIDES = {
    "hardened": [],
    "insecure": [HERE / "compose" / "insecure.yml"],
    "egress-deny": [HERE / "compose" / "egress-deny.yml"],
}
_COMPOSE_PROFILES = {"insecure": ["--profile", "airgap"]}

# Layered on every profile, after its own override: `BLACKBOX_EXTRA_COMPOSE`,
# paths relative to modelbox-ai/ separated by os.pathsep. The Verify Release
# workflow sets it to tests/blackbox/compose/published.yml, so the same checks
# run against the images a release published instead of images built here.
_EXTRA = [ROOT / p for p in os.environ.get("BLACKBOX_EXTRA_COMPOSE", "").split(os.pathsep) if p]

DEV_EMAIL = "dev@modelbox.ai"
DEV_PASSWORD = "password123"
SHIPPED_JWT_SECRET = "dev-secret-change-me"
SHIPPED_POSTGRES_PASSWORD = "secret"


class CheckFailed(AssertionError):
    """A black-box check found the weakness it looks for. Raised only by `check`."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def weakened_by_insecure(reason: str) -> pytest.MarkDecorator:
    """Mark a check the insecure profile must make fail, and say which weakness."""
    return pytest.mark.weakened_by_insecure(reason=reason)


def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "weakened_by_insecure(reason): the insecure profile must make this check fail",
        "config_a: configuration A (.env.example only); needs no running stack",
        "config_b: configuration B, and the insecure profile",
        "upgrade: an upgraded database; manages its own stack",
        "config_c: configuration C (AIRGAPPED, egress-deny network)",
    ):
        config.addinivalue_line("markers", marker)
    if PROFILE not in _OVERRIDES:
        raise pytest.UsageError(f"BLACKBOX_PROFILE={PROFILE!r}; expected one of {sorted(_OVERRIDES)}")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if PROFILE != "insecure":
        return
    for item in items:
        marker = item.get_closest_marker("weakened_by_insecure")
        if marker is not None:
            item.add_marker(
                pytest.mark.xfail(
                    raises=CheckFailed,
                    strict=True,
                    reason=f"insecure profile: {marker.kwargs['reason']}",
                )
            )


# --- No credential in a report --------------------------------------------------
#
# Every token, API key and password the suite obtains or makes is registered
# here, and so is every secret in `.env` as it is read. A failure report is
# redacted before pytest prints it: an assertion over a request that carried a
# key would otherwise show the key, because pytest renders the expression.
# `backend/tests/test_blackbox_redaction.py` runs a failing test through this
# conftest and checks the output.

REDACTED = "<redacted>"
_SECRETS: set[str] = set()
_ENV_SECRETS = ("JWT_SECRET", "ENCRYPTION_KEY", "POSTGRES_PASSWORD", "MODELBOX_APP_DB_PASSWORD")


def remember_secret(value: str) -> str:
    """Register ``value`` for redaction, and return it."""
    if value and len(value) >= 8:
        _SECRETS.add(value)
    return value


_MIN_FRAGMENT = 8


def redact_secrets(text: str) -> str:
    """``text`` with every registered secret, and every fragment of one down to
    eight characters, replaced. pytest truncates long values in an assertion's
    comparison (``{'X-API-Key':...ctMeR3dactMe'}``), so a whole-string replace
    would leave the tail.

    Linear in the text for the usual case: the secrets present are found by
    their eight-character windows first, and only those are expanded.
    """
    windows = {
        secret[start:start + _MIN_FRAGMENT]: secret
        for secret in _SECRETS
        for start in range(len(secret) - _MIN_FRAGMENT + 1)
    }
    present = {
        windows[text[i:i + _MIN_FRAGMENT]]
        for i in range(len(text) - _MIN_FRAGMENT + 1)
        if text[i:i + _MIN_FRAGMENT] in windows
    }
    if not present:
        return text
    fragments = {
        secret[start:start + size]
        for secret in present
        for size in range(_MIN_FRAGMENT, len(secret) + 1)
        for start in range(len(secret) - size + 1)
    }
    for fragment in sorted(fragments, key=len, reverse=True):
        if fragment in text:
            text = text.replace(fragment, REDACTED)
    return text


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.longrepr is not None and not isinstance(report.longrepr, tuple):
        rendered = str(report.longrepr)
        redacted = redact_secrets(rendered)
        if redacted != rendered:
            report.longrepr = redacted
    report.sections = [(name, redact_secrets(content)) for name, content in report.sections]


# --- The stack ------------------------------------------------------------------


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    for name in _ENV_SECRETS:
        remember_secret(values.get(name, ""))
    return values


def compose_command(*args: str, profile: str = PROFILE) -> list[str]:
    files: list[str] = ["-f", str(BASE_COMPOSE)]
    for override in [*_OVERRIDES[profile], *_EXTRA]:
        files += ["-f", str(override)]
    return [
        "docker", "compose", "--env-file", str(ENV_FILE), *files,
        *_COMPOSE_PROFILES.get(profile, []), *args,
    ]


def compose(
    *args: str, input_text: str | None = None, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose ...` for this profile. The caller reads the result."""
    return subprocess.run(
        compose_command(*args),
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        env={**os.environ, **(extra_env or {})},
        check=False,  # callers assert on the exit code, some expecting a refusal
        timeout=600,
    )


def owner_db_password(env: dict[str, str]) -> str:
    return SHIPPED_POSTGRES_PASSWORD if PROFILE == "insecure" else env["POSTGRES_PASSWORD"]


def psql(
    script: str, *, role: str = "owner", variables: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run SQL in the database container, as the owner or as `modelbox_app`.

    Over TCP to 127.0.0.1 inside the container, so the password is checked; it
    travels in PGPASSWORD, taken from this process's environment by `-e`.
    """
    env = read_env()
    user, password = (
        ("modelbox", owner_db_password(env))
        if role == "owner"
        else ("modelbox_app", env["MODELBOX_APP_DB_PASSWORD"])
    )
    args = ["exec", "-T", "-e", "PGPASSWORD", "postgres-db", "psql", "-h", "127.0.0.1",
            "-U", user, "-d", "modelbox_metadata", "-v", "ON_ERROR_STOP=1", "-At"]
    for name, value in (variables or {}).items():
        args += ["-v", f"{name}={value}"]
    args += ["-f", "-"]
    return compose(*args, input_text=script, extra_env={"PGPASSWORD": password})


def sql_ok(script: str, **kwargs: object) -> str:
    result = psql(script, **kwargs)  # type: ignore[arg-type]
    assert result.returncode == 0, f"setup SQL failed: {result.stderr[-800:]}"
    return result.stdout.strip()


# --- HTTP -----------------------------------------------------------------------


def base_url() -> str:
    return f"http://localhost:{read_env().get('UI_PORT', '3000')}"


def new_client() -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=30)


def wait_for_health(timeout_seconds: int = 240) -> dict:
    deadline = time.time() + timeout_seconds
    last = ""
    with new_client() as probe:
        while time.time() < deadline:
            try:
                response = probe.get("/api/health", timeout=5)
                if response.status_code == 200:
                    return response.json()
                last = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(3)
    raise AssertionError(f"the appliance never answered /api/health: {last}")


@pytest.fixture(scope="session")
def client() -> Iterator[httpx.Client]:
    wait_for_health()
    with new_client() as c:
        yield c


def login(client: httpx.Client, email: str, password: str) -> httpx.Response:
    remember_secret(password)
    return client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )


def token(client: httpx.Client, email: str, password: str) -> str:
    response = login(client, email, password)
    assert response.status_code == 200, f"setup login for {email} failed: {response.status_code}"
    return remember_secret(response.json()["access_token"])


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# --- The people and workspaces the checks need -------------------------------------


@dataclass(frozen=True)
class Account:
    email: str
    password: str
    user_id: str


@dataclass(frozen=True)
class World:
    owner: Account
    viewer: Account
    workspace_a: str
    workspace_b: str
    model_a: str
    model_b: str


def make_appliance_owner(client: httpx.Client) -> Account:
    """The appliance owner, made the way an operator would on this profile.

    Hardened: `create-owner`, install step 2. Insecure: the dev seed already
    made an OWNER, so `create-owner` refuses and the seeded account is
    designated, which is the upgrade path's command.
    """
    email, password = "owner@blackbox.test", remember_secret("bb-" + uuid.uuid4().hex)
    created = compose(
        "exec", "-T", "modelbox-backend", "python", "-m", "app.cli", "create-owner",
        "--email", email, "--workspace-name", "Blackbox A", "--password-stdin",
        input_text=password + "\n",
    )
    if PROFILE == "insecure":
        assert created.returncode == 1 and "An owner already exists" in created.stderr, (
            f"fixture sanity: the insecure profile's seed should make create-owner refuse: "
            f"{created.stderr[-400:]}"
        )
        designated = compose(
            "exec", "-T", "modelbox-backend", "python", "-m", "app.cli",
            "designate-appliance-owner", "--email", DEV_EMAIL,
        )
        assert designated.returncode == 0, f"designate failed: {designated.stderr[-400:]}"
        email, password = DEV_EMAIL, DEV_PASSWORD
    else:
        assert created.returncode == 0, f"create-owner failed: {created.stderr[-400:]}"
    me = client.get("/api/v1/auth/me", headers=bearer(token(client, email, password)))
    assert me.status_code == 200
    return Account(email, password, me.json()["user_id"])


_WORLD_SQL = """
INSERT INTO workspaces (workspace_id, name, created_at) VALUES (:'ws_b', 'Blackbox B', now());
INSERT INTO workspace_members (membership_id, workspace_id, user_id, role)
    VALUES (gen_random_uuid(), :'ws_b', :'owner_id', 'OWNER');
INSERT INTO data_models (model_id, workspace_id, title, current_paradigm, target_dialect,
                         version_number, created_at, updated_at)
    VALUES (:'model_a', :'ws_a', 'Blackbox model A', 'KIMBALL', 'postgres', 1, now(), now()),
           (:'model_b', :'ws_b', 'Blackbox model B', 'KIMBALL', 'postgres', 1, now(), now());
INSERT INTO users (user_id, email, hashed_password, is_active, created_at)
    VALUES (:'viewer_id', 'viewer@blackbox.test', :'viewer_hash', true, now());
"""


@pytest.fixture(scope="session")
def world(client: httpx.Client) -> World:
    """An owner of workspaces A and B, a VIEWER of A, and a model in each.

    **The VIEWER joins A through the members API**, as the owner, over HTTP
    (Sprint 8 Step 6; owner decision). Written as the database owner, the way
    an operator would repair an install, are only the rows no API creates:
    workspace B and its first OWNER (there is no create-workspace endpoint,
    and a workspace's first OWNER cannot be added by a member of it), the
    viewer's user row (users come from OIDC, SCIM or create-owner, none of
    which gives this suite a password login), and the two models. Every check
    then runs over HTTP.
    """
    owner = make_appliance_owner(client)
    workspaces = client.get(
        "/api/v1/workspaces", headers=bearer(token(client, owner.email, owner.password))
    ).json()
    assert len(workspaces) == 1, f"fixture sanity: the owner starts in one workspace: {workspaces}"
    ws_a = workspaces[0]["workspace_id"]
    ws_b, model_a, model_b, viewer_id = (str(uuid.uuid4()) for _ in range(4))
    viewer_password = remember_secret("bb-" + uuid.uuid4().hex)
    viewer_hash = bcrypt.hashpw(viewer_password.encode(), bcrypt.gensalt()).decode()
    sql_ok(
        _WORLD_SQL,
        variables={
            "ws_a": ws_a, "ws_b": ws_b, "owner_id": owner.user_id, "model_a": model_a,
            "model_b": model_b, "viewer_id": viewer_id, "viewer_hash": viewer_hash,
        },
    )
    joined = client.post(
        f"/api/v1/workspaces/{ws_a}/members",
        json={"email": "viewer@blackbox.test", "role": "VIEWER"},
        headers=bearer(token(client, owner.email, owner.password)),
    )
    assert joined.status_code == 201, f"setup: the owner could not add the viewer: {joined.text[:300]}"
    viewer = Account("viewer@blackbox.test", viewer_password, viewer_id)
    return World(owner, viewer, ws_a, ws_b, model_a, model_b)
