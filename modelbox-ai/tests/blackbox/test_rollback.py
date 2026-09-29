"""Rollback to the previous release: downgrade, then run its published images.

The CI job starts this release's appliance (hardened) and runs this alone.
The test gives the database what this release adds: imported models with a
composite primary key (Oracle HR's JOB_HISTORY) and a composite foreign key
(AdventureWorks' SalesOrderDetail to SpecialOfferProduct), their dictionary
attestations, and a member whose role was changed through the members API.
It then stops the application, downgrades the schema with this release's own
Alembic to the previous release's migration head, and starts the previous
release's images, pulled from GHCR, against that same database.

What must hold: the previous release starts, serves /health naming its own
version, and reads both models; the member keeps the role it was given. What
the downgrade gives up is asserted too, by SQL, so the release notes' list of
losses is a list of observed facts:

* this release's tables are gone (keys and constraints, relationship column
  pairs, conversion findings, classification scales and levels, attestations);
* a composite foreign key keeps only its first column pair;
* a composite primary key survives as flags on its columns; its key order
  becomes the columns' order in the table.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import (
    ROOT,
    World,
    bearer,
    check,
    compose,
    import_fixture,
    sql_ok,
    token,
    wait_for_health,
)

pytestmark = pytest.mark.rollback

PREVIOUS = "1.11.1"
PREVIOUS_HEAD = "0022_append_only_ledgers"
PUBLISHED = str(ROOT / "tests" / "blackbox" / "compose" / "published.yml")
RELEASE = {"MODELBOX_RELEASE": PREVIOUS}

_THIS_RELEASE_TABLES = (
    "entity_constraints", "entity_constraint_columns", "relationship_columns",
    "model_conversion_findings", "classification_scales", "classification_levels",
    "field_attestations",
)

_COMPOSITE_FK = """
SELECT count(*) FROM relationship_columns p
JOIN entity_relationships r ON r.relationship_id = p.relationship_id
JOIN model_entities f ON f.entity_id = r.from_entity_id
JOIN model_entities t ON t.entity_id = r.to_entity_id
WHERE f.model_id = :'model' AND f.entity_name = 'SalesOrderDetail' AND t.entity_name = 'SpecialOfferProduct';
"""

_FIRST_PAIR_AFTER = """
SELECT fc.column_name || '->' || tc.column_name FROM entity_relationships r
JOIN model_entities f ON f.entity_id = r.from_entity_id
JOIN model_entities t ON t.entity_id = r.to_entity_id
JOIN entity_columns fc ON fc.column_id = r.from_column_id
JOIN entity_columns tc ON tc.column_id = r.to_column_id
WHERE f.model_id = :'model' AND f.entity_name = 'SalesOrderDetail' AND t.entity_name = 'SpecialOfferProduct';
"""

_JOB_HISTORY_KEY = """
SELECT string_agg(c.column_name, ',' ORDER BY c.column_name) FROM entity_columns c
JOIN model_entities e ON e.entity_id = c.entity_id
WHERE e.model_id = :'model' AND e.entity_name = 'JOB_HISTORY' AND c.is_primary_key;
"""


def _exists(table: str) -> bool:
    return sql_ok(f"SELECT to_regclass('public.{table}') IS NOT NULL;") == "t"


def test_the_previous_release_runs_on_a_downgraded_database(client: httpx.Client, world: World) -> None:
    owner = bearer(token(client, world.owner.email, world.owner.password))

    # --- What this release adds -------------------------------------------------
    hr = import_fixture(client, world, "oracle/hr.sql", "oracle")["model_id"]
    aw = import_fixture(client, world, "tsql/adventureworks.sql", "tsql")["model_id"]
    changed = client.patch(f"/api/v1/workspaces/{world.workspace_a}/members/{world.viewer.user_id}",
                           json={"role": "MEMBER"}, headers=owner)
    assert changed.status_code == 200, f"setup: the role change got HTTP {changed.status_code}: {changed.text[:200]}"

    assert sql_ok(_COMPOSITE_FK, variables={"model": aw}) == "2", "fixture sanity: AdventureWorks' composite FK"
    assert int(sql_ok("SELECT count(*) FROM field_attestations;")) > 0, "fixture sanity: attestations exist"
    assert all(_exists(t) for t in _THIS_RELEASE_TABLES), "fixture sanity: this release's tables exist"

    # --- Downgrade with this release's Alembic, the application stopped ---------
    stopped = compose("stop", "modelbox-ui", "modelbox-backend", "modelbox-worker")
    assert stopped.returncode == 0, f"setup: stopping the application: {stopped.stderr[-400:]}"
    down = compose("run", "--rm", "--no-deps", "modelbox-migrate",
                   "python", "-m", "alembic", "downgrade", PREVIOUS_HEAD)
    check(down.returncode == 0, f"alembic downgrade {PREVIOUS_HEAD}: {down.stderr[-800:]}")
    at = sql_ok("SELECT version_num FROM alembic_version;")
    check(at == PREVIOUS_HEAD, f"after the downgrade the database is at {at!r}")

    # --- What the downgrade gives up, read by SQL -------------------------------
    remaining = [t for t in _THIS_RELEASE_TABLES if _exists(t)]
    check(remaining == [], f"tables still present after the downgrade: {remaining}")
    # (SpecialOfferID, ProductID) -> SpecialOfferProduct keeps its first pair only.
    pair = sql_ok(_FIRST_PAIR_AFTER, variables={"model": aw})
    check(pair == "SpecialOfferID->SpecialOfferID", f"the composite FK kept {pair!r}")
    key = sql_ok(_JOB_HISTORY_KEY, variables={"model": hr})
    check(key == "EMPLOYEE_ID,START_DATE", f"JOB_HISTORY's key columns after the downgrade: {key!r}")

    # --- The previous release's published images, on the same database ---------
    pulled = compose("-f", PUBLISHED, "pull", "modelbox-ui", "modelbox-backend", "modelbox-worker",
                     "modelbox-migrate", extra_env=RELEASE)
    assert pulled.returncode == 0, f"setup: pulling v{PREVIOUS}: {pulled.stderr[-600:]}"
    started = compose("-f", PUBLISHED, "up", "-d", "--no-build", extra_env=RELEASE)
    check(started.returncode == 0, f"v{PREVIOUS} did not start: {started.stderr[-800:]}")
    health = wait_for_health()
    check(health.get("status") == "ok" and health.get("version") == PREVIOUS, f"/health from v{PREVIOUS}: {health}")
    at = sql_ok("SELECT version_num FROM alembic_version;")
    check(at == PREVIOUS_HEAD, f"v{PREVIOUS}'s migrate service left the database at {at!r}")

    owner = bearer(token(client, world.owner.email, world.owner.password))
    read_hr = client.get(f"/api/v1/model/{hr}", headers=owner)
    check(read_hr.status_code == 200, f"v{PREVIOUS} reading the HR model: HTTP {read_hr.status_code}")
    entities = {e["entity_name"]: e for e in read_hr.json()["entities"]}
    check(len(entities) == 7, f"v{PREVIOUS} read {len(entities)} HR tables")
    keys = sorted(c["name"] for c in entities["JOB_HISTORY"]["columns"] if c["is_primary_key"])
    check(keys == ["EMPLOYEE_ID", "START_DATE"], f"v{PREVIOUS} reads JOB_HISTORY's key as {keys}")
    read_aw = client.get(f"/api/v1/model/{aw}", headers=owner, timeout=120)
    check(read_aw.status_code == 200, f"v{PREVIOUS} reading the AdventureWorks model: HTTP {read_aw.status_code}")

    role = sql_ok("SELECT role FROM workspace_members WHERE workspace_id = :'ws' AND user_id = :'user';",
                  variables={"ws": world.workspace_a, "user": world.viewer.user_id})
    check(role == "MEMBER", f"the changed role after the rollback: {role!r}")
