"""Rollback to the previous release: downgrade, then run its published images.

The CI job starts this release's appliance (hardened) and runs this alone.
The test gives the database what this release adds (migrations 0028 to 0031):

* imported models whose columns hold identity seeds and computed-column
  expressions (AdventureWorks) and whose model holds sequences (Pagila);
* a source-to-target mapping with an entry a person wrote, and so a row in
  the append-only decisions record;
* suggestions run on AdventureWorks, one accepted with a PII type added in
  0031 (`DATE_OF_BIRTH`) and one with a type the previous release reads
  (`EMAIL`).

It then stops the application, downgrades the schema with this release's own
Alembic to the previous release's migration head, and starts the previous
release's images, pulled from GHCR, against that same database.

What must hold: the previous release starts, serves /health naming its own
version, and reads the models, including the column whose PII type was
cleared. What the downgrade gives up, and what it keeps, is asserted by SQL, so
the release notes' lists are lists of observed facts:

* lost: the mapping documents, entries and proposals; the suggestions; each
  column's identity and computed expression, and each model's sequences; a PII
  type the previous release cannot read (the column stays PII, and the change
  is listed as a conversion finding);
* kept: the mapping decisions record, a PII type the previous release reads,
  and the audit events of this release's actions.
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

PREVIOUS = "1.12.0"
PREVIOUS_HEAD = "0027_member_audit_actions"
PUBLISHED = str(ROOT / "tests" / "blackbox" / "compose" / "published.yml")
RELEASE = {"MODELBOX_RELEASE": PREVIOUS}

#: This release's tables that a downgrade to the previous head drops.
_DROPPED_TABLES = ("mapping_documents", "mapping_entries", "mapping_entry_sources", "mapping_proposals",
                   "model_suggestions")
#: This release's columns that a downgrade drops, as (table, column).
_DROPPED_COLUMNS = (("entity_columns", "identity"), ("entity_columns", "computed_expression"),
                    ("entity_columns", "computed_persisted"), ("data_models", "sequences"))

_COLUMN_PII = """
SELECT c.is_pii::text || ',' || coalesce(c.pii_type, '') FROM entity_columns c
JOIN model_entities e ON e.entity_id = c.entity_id
WHERE e.model_id = :'model' AND e.entity_name = :'entity' AND c.column_name = :'column';
"""


def _exists(table: str) -> bool:
    return sql_ok(f"SELECT to_regclass('public.{table}') IS NOT NULL;") == "t"


def _has_column(table: str, column: str) -> bool:
    return sql_ok("SELECT count(*) FROM information_schema.columns WHERE table_name = :'t' AND column_name = :'c';",
                  variables={"t": table, "c": column}) == "1"


def _count(query: str, **variables: str) -> int:
    return int(sql_ok(query, variables=variables))


def _pii(model: str, entity: str, column: str) -> str:
    return sql_ok(_COLUMN_PII, variables={"model": model, "entity": entity, "column": column})


def _ok(response: httpx.Response, what: str, *codes: int) -> dict:
    assert response.status_code in codes, f"setup: {what} got HTTP {response.status_code}: {response.text[:300]}"
    return response.json() if response.content else {}


def _accept(client: httpx.Client, owner: dict[str, str], model: str, suggestions: list[dict], entity: str,
            column: str, category: str) -> None:
    found = [s for s in suggestions if (s["entity"], s["column"], s["category"]) == (entity, column, category)]
    assert len(found) == 1, f"setup: one {category} suggestion on {entity}.{column}, got {len(found)}"
    _ok(client.post(f"/api/v1/model/{model}/suggestions/{found[0]['suggestion_id']}/accept", headers=owner),
        f"accepting {entity}.{column}", 200)


def test_the_previous_release_runs_on_a_downgraded_database(client: httpx.Client, world: World) -> None:
    owner = bearer(token(client, world.owner.email, world.owner.password))

    # --- What this release adds -------------------------------------------------
    hr = import_fixture(client, world, "oracle/hr.sql", "oracle")["model_id"]
    aw = import_fixture(client, world, "tsql/adventureworks.sql", "tsql")["model_id"]
    pagila = import_fixture(client, world, "postgres/pagila.sql", "postgres")["model_id"]

    document = _ok(client.post(f"/api/v1/model/{hr}/mappings", headers=owner,
                               json={"source_model_id": hr, "title": "HR to itself"}), "creating a mapping", 201)
    _ok(client.post(f"/api/v1/mappings/{document['document']['document_id']}/entries", headers=owner,
                    json={"target": {"entity": "EMPLOYEES", "column": "EMAIL"}, "kind": "mapped",
                          "sources": [{"entity": "EMPLOYEES", "column": "EMAIL"}]}),
        "writing a mapping entry", 201)

    run = _ok(client.post(f"/api/v1/model/{aw}/suggestions", headers=owner, timeout=120),
              "running the suggestion rules", 200)
    _accept(client, owner, aw, run["suggestions"], "Employee", "BirthDate", "DATE_OF_BIRTH")
    _accept(client, owner, aw, run["suggestions"], "EmailAddress", "EmailAddress", "EMAIL")

    assert all(_exists(t) for t in _DROPPED_TABLES), "fixture sanity: this release's tables exist"
    assert _count("SELECT count(*) FROM mapping_entries;") == 1, "fixture sanity: one mapping entry"
    assert _count("SELECT count(*) FROM model_suggestions;") > 0, "fixture sanity: suggestions are stored"
    assert _count("SELECT count(identity) FROM entity_columns;") > 0, "fixture sanity: identity seeds are stored"
    assert _count("SELECT count(computed_expression) FROM entity_columns;") > 0, \
        "fixture sanity: computed expressions are stored"
    assert _count("SELECT count(*) FROM data_models WHERE model_id = :'m' AND sequences IS NOT NULL;", m=pagila) == 1, \
        "fixture sanity: Pagila's sequences are stored"
    assert _pii(aw, "Employee", "BirthDate") == "true,DATE_OF_BIRTH", "fixture sanity: the newer type is stored"
    assert _pii(aw, "EmailAddress", "EmailAddress") == "true,EMAIL", "fixture sanity: the older type is stored"
    decisions = _count("SELECT count(*) FROM mapping_decisions;")
    assert decisions >= 1, "fixture sanity: the decision is recorded"
    audited = _count("SELECT count(*) FROM audit_event WHERE action IN ('MAPPING_DECIDED', 'SUGGESTION_DECIDED');")
    assert audited >= 3, "fixture sanity: the decisions are audit events"

    # --- Downgrade with this release's Alembic, the application stopped ---------
    stopped = compose("stop", "modelbox-ui", "modelbox-backend", "modelbox-worker")
    assert stopped.returncode == 0, f"setup: stopping the application: {stopped.stderr[-400:]}"
    down = compose("run", "--rm", "--no-deps", "modelbox-migrate",
                   "python", "-m", "alembic", "downgrade", PREVIOUS_HEAD)
    check(down.returncode == 0, f"alembic downgrade {PREVIOUS_HEAD}: {down.stderr[-800:]}")
    at = sql_ok("SELECT version_num FROM alembic_version;")
    check(at == PREVIOUS_HEAD, f"after the downgrade the database is at {at!r}")

    # --- What the downgrade gives up, and keeps, read by SQL -------------------
    remaining = [t for t in _DROPPED_TABLES if _exists(t)]
    check(remaining == [], f"tables still present after the downgrade: {remaining}")
    columns = [f"{t}.{c}" for t, c in _DROPPED_COLUMNS if _has_column(t, c)]
    check(columns == [], f"columns still present after the downgrade: {columns}")
    check(_pii(aw, "Employee", "BirthDate") == "true,", "the newer PII type is cleared and the column stays PII")
    check(_pii(aw, "EmailAddress", "EmailAddress") == "true,EMAIL", "a PII type the previous release reads is kept")
    listed = _count("SELECT count(*) FROM model_conversion_findings WHERE model_id = :'m' "
                    "AND revision = '0031_suggestions' AND kind = 'pii_type_cleared';", m=aw)
    check(listed == 1, f"the cleared PII type is listed once, found {listed}")
    # Owner, H3 (0030): the record of who decided what is kept.
    check(_exists("mapping_decisions"), "the downgrade dropped mapping_decisions, which it keeps")
    kept = _count("SELECT count(*) FROM mapping_decisions;")
    check(kept == decisions, f"mapping_decisions held {decisions} rows and now holds {kept}")
    still = _count("SELECT count(*) FROM audit_event WHERE action IN ('MAPPING_DECIDED', 'SUGGESTION_DECIDED');")
    check(still >= audited, f"audit events of this release's decisions: {audited} before, {still} after")

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
    check(len(read_hr.json()["entities"]) == 7, f"v{PREVIOUS} read {len(read_hr.json()['entities'])} HR tables")
    read_pagila = client.get(f"/api/v1/model/{pagila}", headers=owner, timeout=120)
    check(read_pagila.status_code == 200, f"v{PREVIOUS} reading the Pagila model: HTTP {read_pagila.status_code}")
    read_aw = client.get(f"/api/v1/model/{aw}", headers=owner, timeout=120)
    check(read_aw.status_code == 200, f"v{PREVIOUS} reading the AdventureWorks model: HTTP {read_aw.status_code}")
    employee = next(e for e in read_aw.json()["entities"] if e["entity_name"] == "Employee")
    birth = next(c for c in employee["columns"] if c["name"] == "BirthDate")
    check((birth["is_pii"], birth["pii_type"]) == (True, None),
          f"v{PREVIOUS} reads the cleared column as PII with no type: {(birth['is_pii'], birth['pii_type'])}")
