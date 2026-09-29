"""An upgraded database: designate-appliance-owner, then the owner's export.

An appliance upgraded from before v1.11.0 has workspace OWNERs and no
appliance owner. This test builds that database from outside: Postgres alone,
the schema taken to 0019 with the image's own Alembic, a user who is OWNER of
a workspace written at that revision, and then the whole appliance started,
whose migrate service takes it to head. The operator then runs
`designate-appliance-owner`, and that owner's appliance export must show the
designation and the sign-in, with /health reporting no failed audit write.

Manages its own stack; the CI job starts from `down -v` and runs this alone.
"""

from __future__ import annotations

import json
import uuid

import bcrypt
import httpx
import pytest
from conftest import (
    base_url,
    bearer,
    check,
    compose,
    remember_secret,
    sql_ok,
    token,
    wait_for_health,
)

pytestmark = pytest.mark.upgrade

PRE_UPGRADE = "0019_scim_audit_actions"

_SEED_AT_0019 = """
INSERT INTO users (user_id, email, hashed_password, is_active, created_at)
    VALUES (:'user_id', :'email', :'pw_hash', true, now());
INSERT INTO workspaces (workspace_id, name, created_at) VALUES (:'ws', 'Upgraded workspace', now());
INSERT INTO workspace_members (membership_id, workspace_id, user_id, role)
    VALUES (gen_random_uuid(), :'ws', :'user_id', 'OWNER');
"""


def test_designate_on_an_upgraded_database_reaches_the_owners_export() -> None:
    started = compose("up", "-d", "--wait", "postgres-db")
    assert started.returncode == 0, f"setup: postgres: {started.stderr[-400:]}"
    to_0019 = compose(
        "run", "--rm", "--no-deps", "modelbox-migrate",
        "python", "-m", "alembic", "upgrade", PRE_UPGRADE,
    )
    assert to_0019.returncode == 0, f"setup: alembic upgrade {PRE_UPGRADE}: {to_0019.stderr[-600:]}"
    assert sql_ok("SELECT version_num FROM alembic_version;") == PRE_UPGRADE

    email, password = "upgraded-owner@blackbox.test", remember_secret("bb-" + uuid.uuid4().hex)
    sql_ok(
        _SEED_AT_0019,
        variables={
            "user_id": str(uuid.uuid4()), "ws": str(uuid.uuid4()), "email": email,
            "pw_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        },
    )

    # No --wait: the worker has no healthcheck and the migrate service exits by
    # design, so readiness is the UI answering /api/health.
    whole = compose("up", "-d")
    assert whole.returncode == 0, f"setup: the appliance did not start: {whole.stderr[-600:]}"
    wait_for_health()
    assert sql_ok("SELECT version_num FROM alembic_version;") == "0026_dictionary_fields", (
        "fixture sanity: the migrate service took the database to head"
    )

    refused = compose(
        "exec", "-T", "modelbox-backend", "python", "-m", "app.cli", "create-owner",
        "--email", "second@blackbox.test", "--password-stdin",
        input_text=remember_secret("bb-" + uuid.uuid4().hex) + "\n",
    )
    check(refused.returncode == 1 and "An owner already exists" in refused.stderr,
          f"create-owner on an upgraded appliance: exit {refused.returncode}")

    designated = compose(
        "exec", "-T", "modelbox-backend", "python", "-m", "app.cli",
        "designate-appliance-owner", "--email", email,
    )
    check(designated.returncode == 0, f"designate-appliance-owner failed: {designated.stderr[-400:]}")

    with httpx.Client(base_url=base_url(), timeout=30) as client:
        owner = bearer(token(client, email, password))
        export = client.get("/api/v1/audit/appliance-export", headers=owner)
        check(export.status_code == 200, f"the designated owner's export got HTTP {export.status_code}")
        actions = {
            row["action"]
            for row in map(json.loads, export.text.splitlines())
            if row.get("actor_email") == email
        }
        check({"APPLIANCE_OWNER_DESIGNATED", "AUTH_LOGIN"} <= actions,
              f"the upgraded owner's export has {sorted(actions)}")
        health = client.get("/api/health").json()
        check(health["status"] == "ok" and health["audit"]["write_failures"] == 0,
              f"/health reports {health['status']!r}, audit {health['audit']}")
