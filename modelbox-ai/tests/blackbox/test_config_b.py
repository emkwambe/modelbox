"""Configuration B: the appliance as installed, checked from outside.

`.env` from init-env, ENVIRONMENT=production (the appliance compose file sets
it), the owner made with `create-owner`. Every check must pass.

The same file runs against the insecure profile (conftest, Amendment 3). A
check marked `weakened_by_insecure` must then fail on its own check. The
others cover weaknesses no configuration can put back, and each names the
in-process negative control that shows it able to fail:

* VIEWER cannot transform: authorisation is code, not configuration.
  `test_route_policy.py` (the fake unguarded route in a nested router) and
  `test_role_authorization.py`.
* API key scoped to its workspace: `test_api_key_scope.py`
  (`test_negative_control_without_the_workspace_scope_a_key_reaches_b`).
* audit events and /health: `test_audit_sink_unpatched.py`
  (`test_negative_control_without_get_sessionmaker_nothing_is_stored`,
  `test_negative_control_without_the_counter_health_stays_ok`).
* the application role cannot rewrite a ledger: `test_ledger_roles_postgres.py`
  (`test_negative_control_an_extra_ledger_grant_fails_the_check`), on Postgres.

The insecure profile's defaulted database password is not observable from
outside: the database publishes no port in either profile. Its refusal in
production is `test_config_secrets.py` (`postgres_password`) and
`test_appliance_configuration.py`
(`test_negative_control_a_defaulted_secret_fails_the_check[POSTGRES_PASSWORD]`).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import time
import uuid

import httpx
import pytest
from conftest import (
    DEV_EMAIL,
    DEV_PASSWORD,
    SHIPPED_JWT_SECRET,
    World,
    bearer,
    check,
    login,
    psql,
    token,
    weakened_by_insecure,
)

pytestmark = pytest.mark.config_b


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hs256(payload: dict, secret: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


# --- B1: the dev account ----------------------------------------------------------


@weakened_by_insecure("the dev account is seeded in development")
def test_b1_the_dev_account_cannot_sign_in(client: httpx.Client) -> None:
    response = login(client, DEV_EMAIL, DEV_PASSWORD)
    check(response.status_code == 401, f"dev@modelbox.ai signed in: HTTP {response.status_code}")


# --- B2: a token signed with the shipped secret ------------------------------------------


@weakened_by_insecure("JWT_SECRET is the shipped dev-secret-change-me")
def test_b2_a_token_signed_with_the_shipped_secret_is_rejected(
    client: httpx.Client, world: World
) -> None:
    genuine = client.get(
        "/api/v1/auth/me", headers=bearer(token(client, world.owner.email, world.owner.password))
    )
    assert genuine.status_code == 200, "fixture sanity: a real token for the owner works"
    forged = _hs256({"sub": world.owner.user_id, "exp": int(time.time()) + 3600}, SHIPPED_JWT_SECRET)
    response = client.get("/api/v1/auth/me", headers=bearer(forged))
    check(response.status_code == 401, f"a token signed with the shipped secret got HTTP {response.status_code}")


# --- B3: nothing but the UI is published -------------------------------------------------


def _reachable(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


@pytest.mark.parametrize(
    "port",
    [
        pytest.param(4000, id="4000"),
        pytest.param(8000, id="8000-backend", marks=weakened_by_insecure("the backend port is published")),
        pytest.param(11434, id="11434-ollama", marks=weakened_by_insecure("the Ollama port is published")),
        pytest.param(5432, id="5432-postgres"),
        pytest.param(6379, id="6379-redis"),
    ],
)
def test_b3_only_the_ui_port_is_reachable(client: httpx.Client, port: int) -> None:
    assert _reachable(int(client.base_url.port)), "fixture sanity: the UI port answers"
    check(not _reachable(port), f"127.0.0.1:{port} is reachable from the host")


# --- B4: self-registration --------------------------------------------------------------


@weakened_by_insecure("self-registration is open in development")
def test_b4_self_registration_is_refused(client: httpx.Client) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"walk-in-{uuid.uuid4().hex[:8]}@blackbox.test", "password": "walk-in-" + uuid.uuid4().hex},
    )
    check(response.status_code == 403, f"POST /auth/register got HTTP {response.status_code}")


# --- B5: a VIEWER cannot transform ----------------------------------------------------------


def test_b5_a_viewer_cannot_transform_a_model(client: httpx.Client, world: World) -> None:
    viewer = bearer(token(client, world.viewer.email, world.viewer.password))
    readable = client.get(f"/api/v1/model/{world.model_a}", headers=viewer)
    assert readable.status_code == 200, "fixture sanity: the VIEWER can read the model"
    response = client.post(
        f"/api/v1/model/{world.model_a}/transform-paradigm",
        headers=viewer,
        json={"target_paradigm": "DATA_VAULT"},
    )
    check(response.status_code == 403, f"a VIEWER's transform-paradigm got HTTP {response.status_code}")


# --- B6: an API key stays in its workspace ------------------------------------------------


def test_b6_a_key_minted_in_a_is_refused_in_b(client: httpx.Client, world: World) -> None:
    owner = bearer(token(client, world.owner.email, world.owner.password))
    minted = client.post(
        "/api/v1/auth/api-keys",
        headers=owner,
        json={"name": "blackbox", "workspace_id": world.workspace_a},
    )
    assert minted.status_code == 201, f"setup: minting a key got HTTP {minted.status_code}"
    key = {"X-API-Key": minted.json()["api_key"]}
    assert client.get(f"/api/v1/model/{world.model_a}", headers=key).status_code == 200, (
        "fixture sanity: the key works in its own workspace"
    )
    assert client.get(f"/api/v1/model/{world.model_b}", headers=owner).status_code == 200, (
        "fixture sanity: the key's creator can read workspace B"
    )
    response = client.get(f"/api/v1/model/{world.model_b}", headers=key)
    check(response.status_code == 403, f"a key from workspace A read workspace B: HTTP {response.status_code}")


# --- B7: sign-ins are audited, and the sink is healthy ---------------------------------------


def test_b7_sign_ins_reach_the_owners_export_and_health_is_ok(
    client: httpx.Client, world: World
) -> None:
    failed = login(client, world.owner.email, "not-the-password")
    assert failed.status_code == 401, "setup: a wrong password is refused"
    owner = bearer(token(client, world.owner.email, world.owner.password))
    export = client.get("/api/v1/audit/appliance-export", headers=owner)
    assert export.status_code == 200, f"setup: the appliance export got HTTP {export.status_code}"
    mine = {
        row["action"]
        for row in map(json.loads, export.text.splitlines())
        if row.get("actor_email") == world.owner.email
    }
    check({"AUTH_LOGIN", "AUTH_LOGIN_FAILED"} <= mine, f"the owner's export has {sorted(mine)}")
    health = client.get("/api/health").json()
    check(
        health["status"] == "ok" and health["audit"]["write_failures"] == 0,
        f"/health reports {health['status']!r}, audit {health['audit']}",
    )


# --- B8: the application role cannot rewrite a ledger ----------------------------------------


def test_b8_the_application_role_cannot_update_the_egress_ledger(client: httpx.Client) -> None:
    readable = psql("SELECT count(*) FROM egress_audit;", role="app")
    assert readable.returncode == 0, f"fixture sanity: modelbox_app connects and reads: {readable.stderr[-300:]}"
    rewrite = psql("UPDATE egress_audit SET error = error;", role="app")
    check(
        rewrite.returncode != 0 and "permission denied" in rewrite.stderr,
        f"modelbox_app's UPDATE on egress_audit: exit {rewrite.returncode}, {rewrite.stderr[-200:]!r}",
    )
