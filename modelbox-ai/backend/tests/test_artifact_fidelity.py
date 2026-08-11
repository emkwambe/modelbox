"""Artifact fidelity harness — every emitted artifact, verified by its own consumer.

This module is the executable form of ``docs/PROJECT_STATE_REPORT.md`` §4. Its
premise is that the exporter test suite it sits beside asserts on *strings*::

    assert 'syntax = "proto3";' in proto
    assert "customers_count" in metric_names

Every one of those passes on output that ``dbt parse`` rejects outright, which
is how a non-functional MetricFlow exporter reached ``main`` behind a green
test run. Here, nothing is asserted by substring: DDL is re-parsed by two
independent dialect grammars and executed on a real engine, dbt projects are
handed to ``dbt parse``, Avro to ``fastavro``, Protobuf to ``protoc``, Cube.js
to a JS interpreter.

**Sprint 1 records defects; it does not fix them.** Every known failure is
marked ``xfail`` with its audit finding ID. Sprint 3's completion is defined as
those xfails turning green — a burn-down readable from CI output.

Two properties make that burn-down trustworthy:

``strict=True`` on every defect xfail
    A fix therefore turns the run *red* (XPASS) until the marker is removed, so
    the inventory can never overstate the remaining work, and a repaired
    behaviour can never silently regress afterwards. The Enhancement Blueprint
    §7.3 asks for strict only once an xfail flips; applying it from the start is
    the same guarantee, earlier.

``MODELBOX_FIDELITY_STRICT=1``
    Tests skip cleanly when a toolchain is absent, so this module is useful in
    the app venv too. That is also a hazard: if ``dbt`` failed to install, every
    dbt gate would skip and CI would go green over an unverified exporter. With
    the variable set — as the CI tools job does — a missing toolchain is a hard
    failure instead.

Environments (see ``requirements-dev.txt``): ``backend/.venv`` runs the app and
gets the sqlglot/sqlfluff/duckdb/protoc/node checks; ``backend/.venv-tools``
additionally has dbt and fastavro and is the authoritative full matrix. Never
install one into the other.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.schemas.data_model import ColumnSchema, SynthesizedModel
from app.services.exporter_service import ExporterService
from app.services.seed_generator import SyntheticSeedGenerator

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_GOLD_DIR = _FIXTURES / "gold"
_SYNTHETIC_DIR = _FIXTURES / "synthetic"
_CUBE_INSPECT = _FIXTURES / "_cube_inspect.mjs"
_EXTRACTOR = _GOLD_DIR / "_extract_gold_graphs.mjs"
_TEMPLATES_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "templates.ts"
)


@dataclass(frozen=True)
class Fixture:
    """A model plus the export metadata the API would supply alongside it."""

    id: str
    model: SynthesizedModel
    dataset_name: str
    raw: dict[str, Any]


def _load(path: Path) -> Fixture:
    raw = json.loads(path.read_text(encoding="utf-8"))
    model = SynthesizedModel.model_validate(
        {
            "paradigm": raw["paradigm"],
            "entities": raw["entities"],
            "relationships": raw["relationships"],
        }
    )
    # GET /model/{id}/export/contract passes model.title as dataset_name.
    return Fixture(raw["id"], model, raw.get("dataset_name", raw["id"]), raw)


GOLD: dict[str, Fixture] = {
    f.id: f for f in (_load(p) for p in sorted(_GOLD_DIR.glob("*.json"))
                      if p.name != "index.json")
}
SYNTHETIC: dict[str, Fixture] = {
    f.id: f for f in (_load(p) for p in sorted(_SYNTHETIC_DIR.glob("*.json")))
}

GOLD_IDS = sorted(GOLD)

# Dialect certification — Enhancement Blueprint §3, Q4. `postgres`, `snowflake`,
# `redshift` and `duckdb` are deployment-verified; the other three are Preview
# and are NOT scheduled for repair, so their failures are marked `preview` and
# excluded from the Sprint 3 burn-down.
CERTIFIED_DIALECTS = ("postgres", "snowflake", "redshift", "duckdb")
PREVIEW_DIALECTS = ("bigquery", "databricks", "clickhouse")
ALL_DIALECTS = CERTIFIED_DIALECTS + PREVIEW_DIALECTS


# ---------------------------------------------------------------------------
# Toolchain detection
# ---------------------------------------------------------------------------
_STRICT = os.environ.get("MODELBOX_FIDELITY_STRICT") == "1"

HAVE_DBT = find_spec("dbt") is not None
HAVE_FASTAVRO = find_spec("fastavro") is not None
HAVE_DUCKDB = find_spec("duckdb") is not None
HAVE_SQLFLUFF = find_spec("sqlfluff") is not None
PROTOC = shutil.which("protoc")
NODE = shutil.which("node")


def _need(available: object, tool: str) -> None:
    """Skip when a toolchain is absent — unless strict mode forbids skipping.

    Without the strict gate a failed CI install would make every dependent test
    skip, and the pipeline would go green having verified nothing.
    """
    if available:
        return
    message = f"{tool} not available in this environment"
    if _STRICT:
        pytest.fail(
            f"MODELBOX_FIDELITY_STRICT=1 but {message}. The fidelity gate must "
            f"not pass by skipping; install backend/requirements-dev.txt."
        )
    pytest.skip(message)


def test_strict_mode_has_the_full_toolchain() -> None:
    """Under MODELBOX_FIDELITY_STRICT, assert nothing can silently skip."""
    if not _STRICT:
        pytest.skip("MODELBOX_FIDELITY_STRICT is not set (app-venv run)")
    missing = [
        name
        for name, present in (
            ("dbt", HAVE_DBT),
            ("fastavro", HAVE_FASTAVRO),
            ("duckdb", HAVE_DUCKDB),
            ("sqlfluff", HAVE_SQLFLUFF),
            ("protoc", PROTOC),
            ("node", NODE),
        )
        if not present
    ]
    assert not missing, f"fidelity toolchain incomplete: {', '.join(missing)}"


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------
def _param(
    value: str,
    *extra: object,
    defect: str | None = None,
    preview: bool = False,
    skip: str | None = None,
) -> Any:
    """Build a parametrize entry carrying its finding ID as an xfail reason."""
    marks = []
    if skip is not None:
        marks.append(pytest.mark.skip(reason=skip))
    elif defect is not None:
        marks.append(pytest.mark.xfail(reason=defect, strict=True))
    if preview:
        marks.append(pytest.mark.preview)
    ident = "-".join([value, *(str(e) for e in extra)])
    return pytest.param(value, *extra, id=ident, marks=marks)


def gold_params(defects: dict[str, str] | None = None,
                skips: dict[str, str] | None = None) -> list[Any]:
    """One parameter per gold graph; `defects` maps graph id -> finding ID."""
    defects, skips = defects or {}, skips or {}
    return [
        _param(gid, defect=defects.get(gid), skip=skips.get(gid))
        for gid in GOLD_IDS
    ]


def all_gold(defect: str) -> list[Any]:
    """Every gold graph fails this check for the same reason."""
    return gold_params({gid: defect for gid in GOLD_IDS})


# ---------------------------------------------------------------------------
# Shared exporter helpers
# ---------------------------------------------------------------------------
def exporter() -> ExporterService:
    """Construct the exporter exactly as the API dependency does."""
    return ExporterService()  # dependencies.py:60 — no arguments


def _pk_columns(model: SynthesizedModel) -> set[str]:
    return {c.name for e in model.entities for c in e.columns if c.is_primary_key}


def _fk_columns(model: SynthesizedModel) -> set[str]:
    return {c.name for e in model.entities for c in e.columns if c.is_foreign_key}


def _declared_length(data_type: str) -> int | None:
    match = re.search(r"(?:VAR)?CHAR\s*\(\s*(\d+)\s*\)", data_type, re.I)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# dbt project construction
# ---------------------------------------------------------------------------
_DBT_PROFILE = """modelbox:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: fidelity
      password: fidelity
      dbname: fidelity
      schema: public
      threads: 1
"""

# A time spine is a dbt *project* requirement for any semantic layer, not
# something an exporter emits, so the harness supplies one. Without it every
# MetricFlow parse dies on the time spine before reaching a real defect.
_TIME_SPINE_SQL = "select cast('2020-01-01' as date) as date_day\n"
_TIME_SPINE_YML = """models:
  - name: metricflow_time_spine
    time_spine:
      standard_granularity_column: date_day
    columns:
      - name: date_day
        granularity: day
"""

_SOURCE_RE = re.compile(r"source\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")


def _synthesise_sources(staging_sql: dict[str, str]) -> str:
    """Declare exactly the sources the exporter's own SQL references.

    The exporter emits ``{{ source('raw', 'x') }}`` but no sources file, so a
    generated project cannot parse standalone — finding H9, asserted by
    ``test_dbt_project_is_self_contained``. Every *other* dbt and MetricFlow
    defect would be masked behind that single failure, so the harness supplies
    the declaration here in order to isolate them.

    Derived from the emitted SQL rather than from the model, so a naming bug in
    the exporter cannot be papered over by this scaffolding.
    """
    found: dict[str, set[str]] = {}
    for sql in staging_sql.values():
        for source_name, table in _SOURCE_RE.findall(sql):
            found.setdefault(source_name, set()).add(table)
    doc = {
        "version": 2,
        "sources": [
            {"name": name, "schema": "public",
             "tables": [{"name": t} for t in sorted(tables)]}
            for name, tables in sorted(found.items())
        ],
    }
    return yaml.safe_dump(doc, sort_keys=False)


def _write_dbt_project(
    root: Path, fixture: Fixture, *, with_semantic: bool, with_sources: bool = True
) -> Path:
    """Materialise a dbt project from the exporter's output."""
    staging = root / "models" / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    files = exporter().generate_dbt_project(fixture.model)
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    (root / "dbt_project.yml").write_text(
        f"name: 'fidelity_{fixture.id.replace('-', '_')}'\n"
        "version: '1.0'\nprofile: 'modelbox'\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    (root / "profiles.yml").write_text(_DBT_PROFILE, encoding="utf-8")

    if with_sources:
        sql_only = {k: v for k, v in files.items() if k.endswith(".sql")}
        (staging / "_fidelity_sources.yml").write_text(
            _synthesise_sources(sql_only), encoding="utf-8"
        )

    if with_semantic:
        for path, content in exporter().export_semantic_layer(
            fixture.model, "metricflow"
        ).items():
            (root / "models" / path).write_text(content, encoding="utf-8")
        (root / "models" / "metricflow_time_spine.sql").write_text(
            _TIME_SPINE_SQL, encoding="utf-8"
        )
        (root / "models" / "_time_spine.yml").write_text(
            _TIME_SPINE_YML, encoding="utf-8"
        )
    return root


@dataclass
class DbtResult:
    """Outcome of a `dbt parse`, with the events dbt hides behind a summary."""

    success: bool
    error: str
    events: list[tuple[str, str]]

    def event_names(self) -> set[str]:
        return {name for name, _ in self.events}

    def messages(self, name: str) -> list[str]:
        return [msg for n, msg in self.events if n == name]


# Run in a subprocess, one per project. dbt's flags, adapter registry and
# deprecation "already reported" set are process globals: parsing several
# projects in one interpreter leaks state between them, and a project with no
# deprecations of its own inherits the accumulated DeprecationsSummary of the
# projects parsed before it. That made the result depend on test ordering,
# which would make this gate worthless. Isolation costs ~2s per project.
_DBT_SUBPROCESS = """
import json, sys
from dbt.cli.main import dbtRunner

project = sys.argv[1]
events = []
result = dbtRunner(
    callbacks=[lambda e: events.append((e.info.name, e.info.msg))]
).invoke([
    "parse",
    "--project-dir", project,
    "--profiles-dir", project,
    "--target-path", project + "/target",
    "--log-path", project + "/logs",
    "--no-partial-parse",
])
sys.stdout.write("@@FIDELITY@@" + json.dumps({
    "success": bool(result.success),
    "error": (type(result.exception).__name__ + ": " + str(result.exception))
             if result.exception else "",
    "events": events,
}))
"""


def _run_dbt_parse(project: Path) -> DbtResult:
    """Parse a project in an isolated interpreter, keeping dbt's event stream."""
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
    proc = subprocess.run(
        [sys.executable, "-c", _DBT_SUBPROCESS, str(project)],
        capture_output=True, text=True, env=env, cwd=str(project),
    )
    _, marker, payload = proc.stdout.partition("@@FIDELITY@@")
    if not marker:
        raise AssertionError(
            f"dbt subprocess produced no result (exit {proc.returncode}):\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}"
        )
    raw = json.loads(payload)
    return DbtResult(
        success=raw["success"],
        error=raw["error"],
        events=[(name, msg) for name, msg in raw["events"]],
    )


_DBT_CACHE: dict[tuple[str, bool, bool], DbtResult] = {}


def dbt_parse(
    fixture: Fixture, tmp_path_factory: pytest.TempPathFactory,
    *, with_semantic: bool, with_sources: bool = True,
) -> DbtResult:
    """Cached `dbt parse` — each project is built and parsed at most once."""
    key = (fixture.id, with_semantic, with_sources)
    if key not in _DBT_CACHE:
        suffix = ("sem" if with_semantic else "base") + ("" if with_sources else "-bare")
        root = tmp_path_factory.mktemp(f"dbt-{fixture.id[:12]}-{suffix}")
        _write_dbt_project(
            root, fixture, with_semantic=with_semantic, with_sources=with_sources
        )
        _DBT_CACHE[key] = _run_dbt_parse(root)
    return _DBT_CACHE[key]


# ===========================================================================
# 0. The fixtures themselves cannot drift
# ===========================================================================
def test_gold_mirror_matches_templates_ts(tmp_path: Path) -> None:
    """The committed gold JSON must equal what templates.ts produces today.

    `frontend/src/lib/templates.ts` is the single source of truth for the five
    gold graphs. Re-running the extractor and diffing makes silent drift
    impossible — the same set-equality property `test_trainer_labs.py` uses to
    keep the Trainer honest.
    """
    _need(NODE, "node")
    staging = tmp_path / "gold"
    staging.mkdir()
    # Run the extractor in place, writing elsewhere: it resolves templates.ts
    # relative to its own location, and it must not overwrite the mirror it is
    # being diffed against.
    proc = subprocess.run(
        [str(NODE), "--experimental-strip-types", str(_EXTRACTOR), str(staging)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"extractor failed: {proc.stderr[-2000:]}"

    for regenerated in sorted(staging.glob("*.json")):
        committed = _GOLD_DIR / regenerated.name
        assert committed.is_file(), (
            f"{regenerated.name} exists in templates.ts but not in the mirror; "
            f"re-run {_EXTRACTOR.name}"
        )
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
            regenerated.read_text(encoding="utf-8")
        ), f"gold mirror is stale for {regenerated.stem}; re-run {_EXTRACTOR.name}"


def test_templates_ts_is_the_only_gold_source() -> None:
    """Guard the mirror's provenance: five graphs, extracted, none hand-added."""
    assert _TEMPLATES_TS.is_file()
    index = json.loads((_GOLD_DIR / "index.json").read_text(encoding="utf-8"))
    assert set(index) == set(GOLD_IDS)
    assert len(GOLD_IDS) == 5, "the Requirements Library is five gold graphs"


# ===========================================================================
# 1. DDL
# ===========================================================================
@pytest.mark.parametrize("dialect", ALL_DIALECTS)
@pytest.mark.parametrize("gid", GOLD_IDS)
def test_ddl_reparses(gid: str, dialect: str) -> None:
    """Emitted DDL must re-parse in its own dialect with no opaque fallback.

    sqlglot degrades unrecognised input to a `Command` node rather than raising,
    so a passing transpile proves nothing on its own.
    """
    import sqlglot

    ddl = exporter().generate_ddl(GOLD[gid].model, dialect)
    trees = [t for t in sqlglot.parse(ddl, read=dialect) if t is not None]
    assert trees, "no statements parsed"
    opaque = [t.sql(dialect=dialect) for t in trees if t.key == "command"]
    assert not opaque, f"sqlglot fell back to opaque Command: {opaque[:2]}"
    creates = [t for t in trees if t.key == "create"]
    assert len(creates) == len(GOLD[gid].model.entities)


@pytest.mark.parametrize(
    "dialect",
    [_param(d) for d in CERTIFIED_DIALECTS]
    + [
        _param(
            d,
            defect="H3/Q4: preview dialect — emitted DDL is not accepted by this "
                   "engine's grammar (BigQuery needs NOT ENFORCED on key "
                   "constraints; Databricks needs NOT NULL on primary keys; "
                   "ClickHouse needs ENGINE = and forbids Nullable in a key). "
                   "Blueprint Q4: labelled Preview, not scheduled for repair.",
            preview=True,
        )
        for d in PREVIEW_DIALECTS
    ],
)
@pytest.mark.parametrize("gid", GOLD_IDS)
def test_ddl_dialect_grammar(gid: str, dialect: str) -> None:
    """A second, stricter grammar must also accept the DDL.

    sqlglot is permissive by design. sqlfluff carries per-dialect grammars and
    independently reproduces the certified/preview boundary of Blueprint Q4,
    which turns dialect certification from a judgement call into evidence.
    """
    _need(HAVE_SQLFLUFF, "sqlfluff")
    from sqlfluff.core import FluffConfig, Linter

    ddl = exporter().generate_ddl(GOLD[gid].model, dialect)
    linter = Linter(config=FluffConfig(overrides={"dialect": dialect,
                                                  "rules": "none"}))
    parsed = linter.parse_string(ddl)
    assert parsed.tree is not None, "sqlfluff produced no parse tree"
    unparsable = [s.raw[:200] for s in parsed.tree.recursive_crawl("unparsable")]
    assert not unparsable, (
        f"{dialect} grammar rejected {len(unparsable)} segment(s): {unparsable[:1]}"
    )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_ddl_executes_on_duckdb(gid: str) -> None:
    """Real deployability, not a parser proxy: DuckDB runs the emitted DDL.

    DuckDB is the one certified dialect whose engine is embeddable, so this is
    the strongest artifact claim the product currently owns.
    """
    _need(HAVE_DUCKDB, "duckdb")
    import duckdb

    ddl = exporter().generate_ddl(GOLD[gid].model, "duckdb")
    con = duckdb.connect(":memory:")
    try:
        con.execute(ddl)
        created = {r[0] for r in con.execute(
            "select table_name from information_schema.tables"
        ).fetchall()}
    finally:
        con.close()
    assert created == {e.entity_name for e in GOLD[gid].model.entities}


@pytest.mark.parametrize("gid", all_gold(
    "H4/H3: no NOT NULL is emitted anywhere. A primary key is non-nullable by "
    "definition and Databricks rejects a PK on a nullable column; the general "
    "case needs ColumnSchema.is_nullable from Sprint 2."
))
def test_ddl_primary_key_columns_are_not_null(gid: str) -> None:
    """PK columns must be emitted NOT NULL."""
    model = GOLD[gid].model
    ddl = exporter().generate_ddl(model, "postgres")
    for entity in model.entities:
        for column in entity.columns:
            if not column.is_primary_key:
                continue
            pattern = rf"\b{re.escape(column.name)}\b[^,\n]*NOT NULL"
            assert re.search(pattern, ddl, re.I), (
                f"{entity.entity_name}.{column.name} is a primary key but is "
                f"not emitted NOT NULL"
            )


@pytest.mark.parametrize("gid", gold_params(
    {
        gid: "H5: generate_ddl iterates model.entities in declaration order and "
             "never calls GraphEngine.topological_order, so a child table can be "
             "created before the parent it references."
        for gid in GOLD_IDS
    },
    skips={"marketing-attribution": "single-entity OBT model has no FK ordering"},
))
def test_ddl_order_is_topological(gid: str) -> None:
    """Referenced tables must be created before the tables referencing them."""
    original = GOLD[gid].model
    # Reverse declaration order: the templates happen to be authored parent-first,
    # which is the only reason this defect is invisible today.
    reversed_model = SynthesizedModel(
        paradigm=original.paradigm,
        entities=list(reversed(original.entities)),
        relationships=original.relationships,
    )
    ddl = exporter().generate_ddl(reversed_model, "postgres")
    order = re.findall(r"CREATE TABLE (\w+)", ddl)
    position = {name: i for i, name in enumerate(order)}
    for rel in original.relationships:
        child = rel.from_ref.split(".", 1)[0]
        parent = rel.to_ref.split(".", 1)[0]
        if child == parent or child not in position or parent not in position:
            continue
        assert position[parent] < position[child], (
            f"{child} references {parent} but is created first — "
            f"emitted order {order}"
        )


# ===========================================================================
# 2. dbt
# ===========================================================================
@pytest.mark.parametrize("gid", GOLD_IDS)
def test_dbt_parses(gid: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    """The generated dbt project must parse (harness-supplied sources aside)."""
    _need(HAVE_DBT, "dbt-core")
    result = dbt_parse(GOLD[gid], tmp_path_factory, with_semantic=False)
    assert result.success, result.error


@pytest.mark.parametrize("gid", all_gold(
    "H9: generate_dbt_project emits staging models referencing "
    "{{ source('raw', ...) }} but never emits a sources declaration, so the "
    "project cannot parse standalone. Not recorded in the audit — §4.2 reported "
    "dbt as parsing because the audit harness supplied a sources file itself."
))
def test_dbt_project_is_self_contained(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Exporter output alone, plus only project/profile scaffolding, must parse."""
    _need(HAVE_DBT, "dbt-core")
    result = dbt_parse(
        GOLD[gid], tmp_path_factory, with_semantic=False, with_sources=False
    )
    assert result.success, result.error


@pytest.mark.parametrize("gid", gold_params({
    gid: "M11: generic tests are emitted with top-level arguments; dbt 1.11 "
         "requires them nested under `arguments:`."
    for gid in GOLD_IDS if gid != "marketing-attribution"
}))
def test_dbt_no_deprecations(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A generated project must not rely on deprecated dbt syntax."""
    _need(HAVE_DBT, "dbt-core")
    result = dbt_parse(GOLD[gid], tmp_path_factory, with_semantic=False)
    deprecations = sorted(n for n in result.event_names() if "Deprecation" in n)
    assert not deprecations, f"dbt reported {deprecations}"


@pytest.mark.xfail(
    reason="M7: _dbt_quality_tests emits dbt_expectations.* tests but "
           "generate_dbt_project never emits a packages.yml declaring the "
           "dependency, so the project cannot resolve its own tests.",
    strict=True,
)
def test_dbt_declares_packages_yml() -> None:
    """A project using dbt_expectations must declare it in packages.yml."""
    files = exporter().generate_dbt_project(SYNTHETIC["quality-rules"].model)
    schema_yml = files["models/staging/schema.yml"]
    assert "dbt_expectations." in schema_yml, "fixture no longer exercises M7"
    assert any(p.endswith("packages.yml") for p in files), (
        "emits dbt_expectations tests but declares no packages.yml"
    )


# ===========================================================================
# 3. MetricFlow
# ===========================================================================
def _metricflow_doc(fixture: Fixture) -> dict[str, Any]:
    files = exporter().export_semantic_layer(fixture.model, "metricflow")
    return yaml.safe_load(files["semantic_models.yml"])


@pytest.mark.parametrize("gid", all_gold(
    "B1: MetricFlow output does not parse in dbt. Four independent defects — "
    "missing metric `label`; model ref points at '{name}' where the dbt "
    "exporter emits 'stg_{name}'; `avg` is not a MetricFlow AggregationType; "
    "no defaults.agg_time_dimension."
))
def test_metricflow_parses_in_dbt(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The headline assertion: dbt accepts the emitted semantic layer."""
    _need(HAVE_DBT, "dbt-core")
    result = dbt_parse(GOLD[gid], tmp_path_factory, with_semantic=True)
    detail = "; ".join(result.messages("SemanticValidationFailure"))[:600]
    assert result.success, f"{result.error} {detail}"


@pytest.mark.parametrize("gid", all_gold(
    "B1: metrics are emitted without `label`, which dbt requires."
))
def test_metricflow_metrics_have_label(gid: str) -> None:
    doc = _metricflow_doc(GOLD[gid])
    missing = [m["name"] for m in doc.get("metrics", []) if not m.get("label")]
    assert not missing, f"metrics without a label: {missing}"


@pytest.mark.parametrize("gid", all_gold(
    "B1: semantic models reference ref('{entity}') but generate_dbt_project "
    "names its models stg_{entity} — the two exporters disagree about their "
    "own naming convention."
))
def test_metricflow_ref_matches_dbt_model_name(gid: str) -> None:
    fixture = GOLD[gid]
    dbt_models = {
        Path(p).stem
        for p in exporter().generate_dbt_project(fixture.model)
        if p.endswith(".sql")
    }
    for semantic_model in _metricflow_doc(fixture).get("semantic_models", []):
        referenced = re.search(r"ref\(\s*'([^']+)'\s*\)", semantic_model["model"])
        assert referenced, f"unparseable model ref: {semantic_model['model']!r}"
        assert referenced.group(1) in dbt_models, (
            f"semantic model '{semantic_model['name']}' references "
            f"'{referenced.group(1)}', which the dbt exporter does not emit; "
            f"available: {sorted(dbt_models)}"
        )


# MetricFlow's AggregationType enum — dbt-semantic-interfaces.
_METRICFLOW_AGGREGATIONS = {
    "sum", "min", "max", "count_distinct", "sum_boolean",
    "average", "percentile", "median", "count",
}


@pytest.mark.parametrize("gid", gold_params({
    "saas-subscription":
        "B1: dim_plan.list_price declares aggregation 'avg', which is not a "
        "MetricFlow AggregationType ('average'); dbt exits with a traceback "
        "rather than a parse error.",
}))
def test_metricflow_agg_vocabulary_is_valid(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        for measure in semantic_model.get("measures", []):
            assert measure["agg"] in _METRICFLOW_AGGREGATIONS, (
                f"{semantic_model['name']}.{measure['name']} uses "
                f"agg={measure['agg']!r}"
            )


@pytest.mark.parametrize("gid", all_gold(
    "B1: no `defaults.agg_time_dimension` is emitted, so every measure fails "
    "semantic-manifest validation. Needs the Sprint 2 IR field."
))
def test_metricflow_declares_agg_time_dimension(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        if not semantic_model.get("measures"):
            continue
        agg_time = semantic_model.get("defaults", {}).get("agg_time_dimension")
        assert agg_time, (
            f"semantic model '{semantic_model['name']}' declares measures but "
            f"no defaults.agg_time_dimension"
        )


@pytest.mark.parametrize("gid", gold_params({
    "banking-datavault":
        "B1: sat_account_details has no primary-key column, so no primary "
        "entity is emitted and the manifest is rejected. Satellites "
        "legitimately have no single-column PK.",
}))
def test_metricflow_semantic_model_has_primary_entity(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        if not semantic_model.get("dimensions"):
            continue
        kinds = {e["type"] for e in semantic_model.get("entities", [])}
        assert "primary" in kinds or semantic_model.get("primary_entity"), (
            f"semantic model '{semantic_model['name']}' has dimensions but no "
            f"primary entity"
        )


_RESERVED_GRANULARITIES = {
    "nanosecond", "microsecond", "millisecond", "second", "minute", "hour",
    "day", "week", "month", "quarter", "year",
}


@pytest.mark.parametrize("gid", gold_params({
    "saas-subscription":
        "B1: fact_subscription_monthly.month collides with a reserved "
        "MetricFlow time-granularity keyword; the emitter has no name guard.",
}))
def test_metricflow_names_avoid_reserved_granularity(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        for block in ("entities", "dimensions", "measures"):
            for item in semantic_model.get(block, []):
                assert item["name"].lower() not in _RESERVED_GRANULARITIES, (
                    f"{semantic_model['name']}.{item['name']} is a reserved "
                    f"time-granularity keyword"
                )


@pytest.mark.xfail(
    reason="B1: foreign entities are named after the local FK column, so a "
           "role-playing dimension (ship_to_/bill_to_) has no counterpart on "
           "the parent and the join silently does not exist. Latent on the gold "
           "graphs, where every FK name equals its parent's PK name.",
    strict=True,
)
def test_metricflow_foreign_entity_names_parent_primary() -> None:
    """Foreign entity names must match the parent's primary entity name."""
    fixture = SYNTHETIC["role-playing-dimension"]
    doc = _metricflow_doc(fixture)
    by_name = {m["name"]: m for m in doc["semantic_models"]}
    primary_names = {
        m["name"]: next(e["name"] for e in m["entities"] if e["type"] == "primary")
        for m in doc["semantic_models"]
        if any(e["type"] == "primary" for e in m["entities"])
    }
    for rel in fixture.model.relationships:
        child_entity, child_column = rel.from_ref.split(".", 1)
        parent_entity = rel.to_ref.split(".", 1)[0]
        expected = primary_names[parent_entity]
        foreign = [
            e["name"] for e in by_name[child_entity]["entities"]
            if e["type"] == "foreign" and e.get("expr") == child_column
        ]
        assert foreign == [expected], (
            f"{child_entity}.{child_column} -> {parent_entity}: foreign entity "
            f"named {foreign} but must be '{expected}' to join"
        )


# ===========================================================================
# 4. Cube.js
# ===========================================================================
def _inspect_cubes(fixture: Fixture, tmp_path: Path) -> list[dict[str, Any]]:
    """Execute the emitted Cube files and return the objects Cube would see."""
    written = []
    for path, content in exporter().generate_cube_schema(fixture.model).items():
        target = tmp_path / Path(path).name
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    proc = subprocess.run(
        [str(NODE), str(_CUBE_INSPECT), *sorted(written)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"cube inspector failed: {proc.stderr[-1500:]}"
    return json.loads(proc.stdout)


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_cube_is_valid_js(gid: str, tmp_path: Path) -> None:
    """Every emitted cube must execute and define exactly one cube per entity."""
    _need(NODE, "node")
    cubes = _inspect_cubes(GOLD[gid], tmp_path)
    errors = [c for c in cubes if "error" in c]
    assert not errors, f"cube files failed to execute: {errors}"
    assert len(cubes) == len(GOLD[gid].model.entities)
    for cube in cubes:
        assert cube.get("sql_table"), f"{cube['name']} has no sql_table"


@pytest.mark.parametrize("gid", gold_params({
    gid: "M3: every numeric column becomes a measure, so surrogate and foreign "
         "keys are emitted as SUM(). LookML excludes the PK but not FKs; Cube "
         "excludes neither."
    for gid in GOLD_IDS if gid != "banking-datavault"
}))
def test_cube_no_measure_over_key(gid: str, tmp_path: Path) -> None:
    """SUM() over a surrogate or foreign key is never a meaningful measure."""
    _need(NODE, "node")
    keys = _pk_columns(GOLD[gid].model) | _fk_columns(GOLD[gid].model)
    offending = [
        f"{cube['name']}.{measure_name}"
        for cube in _inspect_cubes(GOLD[gid], tmp_path)
        for measure_name, measure in (cube.get("measures") or {}).items()
        if str(measure.get("sql", "")) in keys
        and measure.get("type") in {"sum", "avg", "min", "max"}
    ]
    assert not offending, f"measures aggregate key columns: {offending}"


@pytest.mark.parametrize("gid", gold_params(
    {
        gid: "M3: _cube_type has no boolean branch, so BOOLEAN columns are "
             "typed `string`, though _logical_type and _lookml_type both "
             "handle booleans."
        for gid in ("saas-subscription", "marketing-attribution")
    },
    skips={
        gid: "graph declares no BOOLEAN column"
        for gid in ("ecommerce-orders", "banking-datavault", "healthcare-ehr")
    },
))
def test_cube_boolean_dimensions_are_boolean(gid: str, tmp_path: Path) -> None:
    _need(NODE, "node")
    booleans = {
        c.name for e in GOLD[gid].model.entities for c in e.columns
        if "BOOL" in c.data_type.upper()
    }
    mistyped = [
        f"{cube['name']}.{name}={dim.get('type')}"
        for cube in _inspect_cubes(GOLD[gid], tmp_path)
        for name, dim in (cube.get("dimensions") or {}).items()
        if str(dim.get("sql", "")) in booleans and dim.get("type") != "boolean"
    ]
    assert not mistyped, f"BOOLEAN columns not typed boolean: {mistyped}"


# ===========================================================================
# 5. LookML
#
# No offline LookML parser exists, so these are structural assertions only —
# recorded as UNVERIFIED-by-toolchain in audit §4.5.
# ===========================================================================
@pytest.mark.parametrize("gid", gold_params({
    gid: "M3: LookML excludes the primary key from measures but not foreign "
         "keys, so SUM() over an FK is emitted."
    for gid in ("saas-subscription", "ecommerce-orders", "healthcare-ehr")
}))
def test_lookml_no_measure_over_foreign_key(gid: str) -> None:
    fks = _fk_columns(GOLD[gid].model)
    offending = []
    for path, view in exporter().export_semantic_layer(
        GOLD[gid].model, "lookml"
    ).items():
        for name in fks:
            if re.search(rf"measure: total_{re.escape(name)}\b", view):
                offending.append(f"{path}:total_{name}")
    assert not offending, f"LookML measures aggregate foreign keys: {offending}"


# ===========================================================================
# 6. ODCS
#
# Spec: Open Data Contract Standard v3.1.0 (Bitol).
# https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/fundamentals.md
# Confirmed via context7 on 2026-08-10: current apiVersion is `v3.1.0`; `kind`
# must be `DataContract`; `id`, `version` and `status` are required at the top
# level; `name` is optional. There is no `info:` object — that key belongs to
# the Data Contract Specification (datacontract.com), a different standard.
# ===========================================================================
ODCS_API_VERSION = "v3.1.0"


def _odcs(fixture: Fixture) -> dict[str, Any]:
    files = exporter().export_data_contract(
        fixture.model, "odcs", fixture.dataset_name
    )
    return yaml.safe_load(files["datacontract.yaml"])


@pytest.mark.parametrize("gid", all_gold(
    f"H2: apiVersion is stamped v0.9.3; the current ODCS line is "
    f"{ODCS_API_VERSION}."
))
def test_odcs_apiversion_is_current(gid: str) -> None:
    assert _odcs(GOLD[gid])["apiVersion"] == ODCS_API_VERSION


@pytest.mark.parametrize("gid", all_gold(
    "H2-ext: the contract is a hybrid of two standards. ODCS v3 requires "
    "top-level `version` and `status`, neither of which is emitted, and the "
    "`info:` block it does emit belongs to the rival Data Contract "
    "Specification. The audit under-called this as a bad version stamp."
))
def test_odcs_conforms_to_v3_fundamentals(gid: str) -> None:
    doc = _odcs(GOLD[gid])
    assert doc.get("kind") == "DataContract"
    missing = [key for key in ("id", "version", "status") if key not in doc]
    assert not missing, f"ODCS v3 requires top-level {missing}"
    assert "info" not in doc, (
        "`info:` is a Data Contract Specification key, not ODCS v3"
    )


@pytest.mark.parametrize("gid", all_gold(
    "H2/H4: `required` is emitted as a restatement of is_primary_key, so every "
    "non-PK column is declared optional — including Data Vault load_dts and "
    "record_source. Needs ColumnSchema.is_nullable from Sprint 2."
))
def test_odcs_required_reflects_nullability(gid: str) -> None:
    """`required` must derive from a nullability declaration, not from the PK flag."""
    assert "is_nullable" in ColumnSchema.model_fields, (
        "ColumnSchema cannot express nullability, so `required` cannot be "
        "derived from it (Sprint 2, H4)"
    )
    columns = {
        (e.entity_name, c.name): c
        for e in GOLD[gid].model.entities for c in e.columns
    }
    for table in _odcs(GOLD[gid])["schema"]:
        for prop in table["properties"]:
            column = columns[(table["name"], prop["name"])]
            expected = not getattr(column, "is_nullable")
            assert prop["required"] is expected, (
                f"{table['name']}.{prop['name']}: required={prop['required']} "
                f"but is_nullable={getattr(column, 'is_nullable')}"
            )


# ===========================================================================
# 7. Avro
# ===========================================================================
@pytest.mark.parametrize("gid", GOLD_IDS)
def test_avro_parses(gid: str) -> None:
    """Every emitted Avro record must parse with the reference implementation."""
    _need(HAVE_FASTAVRO, "fastavro")
    import fastavro

    files = exporter().export_data_contract(
        GOLD[gid].model, "avro", GOLD[gid].dataset_name
    )
    assert len(files) == len(GOLD[gid].model.entities)
    for name, content in files.items():
        fastavro.parse_schema(json.loads(content))


# ===========================================================================
# 8. Protobuf
# ===========================================================================
def _proto_files(fixture: Fixture) -> dict[str, str]:
    return exporter().export_data_contract(
        fixture.model, "protobuf", fixture.dataset_name
    )


def _proto_tags(proto: str, message: str) -> dict[str, int]:
    tags: dict[str, int] = {}
    inside = False
    for line in proto.splitlines():
        if line.startswith(f"message {message} "):
            inside = True
            continue
        if inside and line == "}":
            break
        if inside and line.strip():
            parts = line.strip().rstrip(";").split()
            tags[parts[1]] = int(parts[3])
    return tags


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_protobuf_compiles(gid: str, tmp_path: Path) -> None:
    """protoc must accept the emitted contract."""
    _need(PROTOC, "protoc")
    for name, content in _proto_files(GOLD[gid]).items():
        (tmp_path / name).write_text(content, encoding="utf-8")
        proc = subprocess.run(
            [str(PROTOC), f"--proto_path={tmp_path}",
             f"--descriptor_set_out={tmp_path / 'out.desc'}", name],
            capture_output=True, text=True, cwd=tmp_path,
        )
        assert proc.returncode == 0, proc.stderr[-1500:]


@pytest.mark.parametrize("gid", all_gold(
    "H6: field tags come from enumerate() over the column list, so inserting a "
    "column renumbers every later field and breaks wire compatibility with "
    "deployed consumers. ordinal_position is ignored; needs stable_id (Q6)."
))
def test_protobuf_tags_stable_on_insert(gid: str) -> None:
    """Inserting a column must not move any existing field tag."""
    fixture = GOLD[gid]
    before = _proto_files(fixture)[f"{fixture.dataset_name}.proto"]

    mutated = fixture.model.model_copy(deep=True)
    target = mutated.entities[0]
    target.columns.insert(
        1, ColumnSchema(name="inserted_column", data_type="VARCHAR(80)")
    )
    after = _proto_files(
        Fixture(fixture.id, mutated, fixture.dataset_name, fixture.raw)
    )[f"{fixture.dataset_name}.proto"]

    message = ExporterService._to_pascal_case(target.entity_name)
    original = _proto_tags(before, message)
    updated = _proto_tags(after, message)
    moved = {
        name: (tag, updated.get(name))
        for name, tag in original.items() if updated.get(name) != tag
    }
    assert not moved, f"field tags moved after an insertion: {moved}"


@pytest.mark.parametrize("gid", gold_params({
    gid: "H6: NUMERIC/DECIMAL maps to proto `double`, making money a "
         "floating-point field. Avro emits a decimal logical type with "
         "precision and scale from the same column and is the reference."
    for gid in GOLD_IDS if gid != "healthcare-ehr"
}))
def test_protobuf_decimal_is_not_double(gid: str) -> None:
    fixture = GOLD[gid]
    proto = _proto_files(fixture)[f"{fixture.dataset_name}.proto"]
    offending = [
        f"{e.entity_name}.{c.name}({c.data_type})"
        for e in fixture.model.entities for c in e.columns
        if any(t in c.data_type.upper() for t in ("NUMERIC", "DECIMAL", "NUMBER"))
        and re.search(rf"^\s*double {re.escape(c.name)} = \d+;", proto, re.M)
    ]
    assert not offending, f"fixed-point columns emitted as double: {offending}"


@pytest.mark.xfail(
    reason="H6: the proto package name is sanitised via _safe_identifier but "
           "the emitted filename is not, so a model titled 'Untitled Model' "
           "yields 'Untitled Model.proto'.",
    strict=True,
)
def test_protobuf_filename_is_a_safe_identifier() -> None:
    fixture = SYNTHETIC["spaced-title"]
    assert " " in fixture.dataset_name, "fixture no longer exercises H6"
    for name in _proto_files(fixture):
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+\.proto", name), (
            f"emitted filename is not a safe identifier: {name!r}"
        )


# ===========================================================================
# 9. Synthetic seed
# ===========================================================================
def _seed_rows(fixture: Fixture) -> dict[str, list[dict[str, str]]]:
    result = SyntheticSeedGenerator().generate(fixture.model, 25, "csv")
    rows: dict[str, list[dict[str, str]]] = {}
    for entity in fixture.model.entities:
        text = result.files.get(f"{entity.entity_name}.csv")
        if not text:
            continue
        lines = text.strip().split("\n")
        header = lines[0].split(",")
        rows[entity.entity_name] = [
            dict(zip(header, line.split(","))) for line in lines[1:]
        ]
    return rows


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_seed_generation_order_is_fk_safe(gid: str) -> None:
    """Parents must be populated before the children referencing them."""
    fixture = GOLD[gid]
    result = SyntheticSeedGenerator().generate(fixture.model, 5, "sql_insert")
    position = {name: i for i, name in enumerate(result.generation_order)}
    for rel in fixture.model.relationships:
        child = rel.from_ref.split(".", 1)[0]
        parent = rel.to_ref.split(".", 1)[0]
        if child == parent:
            continue
        assert position[parent] <= position[child], (
            f"{child} is seeded before its parent {parent}: "
            f"{result.generation_order}"
        )


@pytest.mark.parametrize("gid", gold_params({
    "healthcare-ehr":
        "H1: the seed generator never reads a column's declared length, so "
        "diagnosis.icd10_code VARCHAR(10) receives 'icd10_code_1' (12 chars) "
        "and the seed cannot be inserted into the DDL emitted beside it.",
}))
def test_seed_respects_declared_length(gid: str) -> None:
    fixture = GOLD[gid]
    rows = _seed_rows(fixture)
    for entity in fixture.model.entities:
        for column in entity.columns:
            limit = _declared_length(column.data_type)
            if limit is None:
                continue
            for row in rows.get(entity.entity_name, []):
                value = row[column.name]
                assert len(value) <= limit, (
                    f"{entity.entity_name}.{column.name} is {column.data_type} "
                    f"but generated {value!r} ({len(value)} chars)"
                )


@pytest.mark.xfail(
    reason="H1: the seed generator ignores min_value, max_value and "
           "regex_pattern, so it emits rows that fail the dbt and ODCS "
           "assertions exported from the same model — `dbt build` fails on the "
           "product's own fixtures.",
    strict=True,
)
def test_seed_respects_quality_rules() -> None:
    """Generated rows must satisfy the contract the same model exports."""
    fixture = SYNTHETIC["quality-rules"]
    rows = _seed_rows(fixture)
    violations: list[str] = []
    for entity in fixture.model.entities:
        for column in entity.columns:
            for row in rows.get(entity.entity_name, []):
                raw = row[column.name]
                if column.min_value is not None and float(raw) < column.min_value:
                    violations.append(f"{column.name}={raw} < {column.min_value}")
                if column.max_value is not None and float(raw) > column.max_value:
                    violations.append(f"{column.name}={raw} > {column.max_value}")
                if column.regex_pattern and not re.match(column.regex_pattern, raw):
                    violations.append(
                        f"{column.name}={raw!r} !~ {column.regex_pattern}"
                    )
    assert not violations, f"seed violates its own contract: {violations[:6]}"
