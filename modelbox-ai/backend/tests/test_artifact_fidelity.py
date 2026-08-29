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

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)
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

# `dbt build` needs the project's packages installed, and `dbt deps` fetches
# them over the network. Downloading inside a test would make this gate able to
# fail because a registry is slow, which is not a gate. The cache is populated
# once by `scripts/refresh_dbt_packages.py` — the same treatment protoc and node
# already get, and `_need` makes its absence fatal under strict mode rather than
# a silent skip.
_DBT_PACKAGE_CACHE = Path(__file__).resolve().parent.parent / ".dbt-packages"
HAVE_DBT_PACKAGES = _DBT_PACKAGE_CACHE.is_dir() and any(
    _DBT_PACKAGE_CACHE.iterdir()
)
_DBT_LOCK_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "dbt" / "package-lock.yml"
)
_DBT_PACKAGES_HINT = (
    "dbt package cache (run: .venv-tools/Scripts/python "
    "scripts/refresh_dbt_packages.py)"
)


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
            (_DBT_PACKAGES_HINT, HAVE_DBT_PACKAGES),
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

def _write_dbt_project(
    root: Path, fixture: Fixture, *, with_semantic: bool
) -> Path:
    """Materialise a dbt project from the exporter's output.

    **No sources scaffolding.** The harness used to synthesise a sources file
    from the emitted SQL, because the exporter declared none and every other
    dbt and MetricFlow defect would otherwise have been masked behind that one
    failure (H9/B14). The exporter now emits its own, and the scaffolding is
    gone rather than merely unused — leaving it would make
    ``test_dbt_project_is_self_contained`` pass for the wrong reason, and dbt
    in fact rejects the duplicate outright.

    What reaches dbt is therefore the exporter's output plus only
    ``dbt_project.yml`` and ``profiles.yml``, which are the consumer's to write.

    The installed packages are copied from the offline cache rather than
    fetched. That is not scaffolding in the H9 sense: the *declaration* is still
    the exporter's own ``packages.yml``, and the cache was built from that same
    file. dbt refuses to load a project whose packages.yml names an uninstalled
    package, so without this the extended gates would fail before reaching the
    defect they exist to catch.
    """
    staging = root / "models" / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    files = exporter().generate_dbt_project(fixture.model)
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    if "packages.yml" in files and HAVE_DBT_PACKAGES:
        shutil.copytree(_DBT_PACKAGE_CACHE, root / "dbt_packages")

    (root / "dbt_project.yml").write_text(
        f"name: 'fidelity_{fixture.id.replace('-', '_')}'\n"
        "version: '1.0'\nprofile: 'modelbox'\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    (root / "profiles.yml").write_text(_DBT_PROFILE, encoding="utf-8")

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


# `dbt build` needs a warehouse. DuckDB is in-process and file-backed, so the
# gate stays offline and needs no container — the same reason
# `test_ddl_executes_on_duckdb` uses it to prove execution rather than parsing.
_DBT_DUCKDB_PROFILE = """modelbox:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: '{path}'
      threads: 1
"""

# dbt derives a schema by concatenating target and custom schema. The seeds
# have to land in exactly the schema the exporter's own `_sources.yml` declares,
# so the harness overrides the macro to use the custom name verbatim. This is
# consumer configuration — where raw tables live is the deployer's decision,
# which is precisely what the emitted sources file says in its description.
_GENERATE_SCHEMA_NAME = """
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
"""

_DBT_BUILD_SUBPROCESS = """
import json, sys
from dbt.cli.main import dbtRunner

project = sys.argv[1]
events = []
runner = dbtRunner(callbacks=[lambda e: events.append((e.info.name, e.info.msg))])
base = [
    "--project-dir", project,
    "--profiles-dir", project,
    "--target-path", project + "/target",
    "--log-path", project + "/logs",
    "--no-partial-parse",
]
# Seeds first, deliberately as a separate invocation. The staging models read
# `source()`, not `ref()`, so dbt has no dependency edge from a seed to the
# model that consumes it and would otherwise build the model before the table
# exists. That is correct dbt modelling on the exporter's part -- staging models
# should read sources -- so the ordering is the harness's problem to solve.
seed = runner.invoke(["seed"] + base)
build = runner.invoke(["build"] + base) if seed.success else seed
sys.stdout.write("@@FIDELITY@@" + json.dumps({
    "success": bool(seed.success and build.success),
    "error": (type(build.exception).__name__ + ": " + str(build.exception))
             if build.exception else "",
    "events": events,
}))
"""


def _write_dbt_seeds(root: Path, fixture: Fixture, rows: int = 8) -> None:
    """Write the product's own generated seed data into the project.

    The whole point of B13: the CSVs are what `SyntheticSeedGenerator` produces
    for this model, and the tests they must survive are what `ExporterService`
    exports for the same model. Neither side is adjusted to suit the other.
    """
    seeds = root / "seeds"
    seeds.mkdir(parents=True, exist_ok=True)
    result = SyntheticSeedGenerator().generate(fixture.model, rows, fmt="csv")
    for name, body in result.files.items():
        (seeds / name).write_text(body, encoding="utf-8")

    macros = root / "macros"
    macros.mkdir(parents=True, exist_ok=True)
    (macros / "generate_schema_name.sql").write_text(
        _GENERATE_SCHEMA_NAME, encoding="utf-8"
    )
    source_schema = yaml.safe_load(
        (root / "models" / "staging" / "_sources.yml").read_text(encoding="utf-8")
    )["sources"][0]["schema"]
    (root / "dbt_project.yml").write_text(
        f"name: 'fidelity_{fixture.id.replace('-', '_')}'\n"
        "version: '1.0'\nprofile: 'modelbox'\nmodel-paths: ['models']\n"
        "seed-paths: ['seeds']\nmacro-paths: ['macros']\n"
        f"seeds:\n  fidelity_{fixture.id.replace('-', '_')}:\n"
        f"    +schema: {source_schema}\n",
        encoding="utf-8",
    )
    (root / "profiles.yml").write_text(
        _DBT_DUCKDB_PROFILE.format(path=(root / "warehouse.duckdb").as_posix()),
        encoding="utf-8",
    )


def _run_dbt_build(project: Path) -> DbtResult:
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
    proc = subprocess.run(
        [sys.executable, "-c", _DBT_BUILD_SUBPROCESS, str(project)],
        capture_output=True, text=True, env=env, cwd=str(project),
    )
    _, marker, payload = proc.stdout.partition("@@FIDELITY@@")
    if not marker:
        raise AssertionError(
            f"dbt build subprocess produced no result (exit {proc.returncode}):\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}"
        )
    raw = json.loads(payload)
    return DbtResult(
        success=raw["success"],
        error=raw["error"],
        events=[(name, msg) for name, msg in raw["events"]],
    )


_DBT_BUILD_CACHE: dict[str, DbtResult] = {}


def dbt_build(
    fixture: Fixture, tmp_path_factory: pytest.TempPathFactory
) -> DbtResult:
    """Seed the product's rows, run every model and every exported test."""
    if fixture.id not in _DBT_BUILD_CACHE:
        root = tmp_path_factory.mktemp(f"build-{fixture.id[:12]}")
        _write_dbt_project(root, fixture, with_semantic=False)
        _write_dbt_seeds(root, fixture)
        _DBT_BUILD_CACHE[fixture.id] = _run_dbt_build(root)
    return _DBT_BUILD_CACHE[fixture.id]


_DBT_CACHE: dict[tuple[str, bool], DbtResult] = {}


def dbt_parse(
    fixture: Fixture, tmp_path_factory: pytest.TempPathFactory,
    *, with_semantic: bool,
) -> DbtResult:
    """Cached `dbt parse` — each project is built and parsed at most once."""
    key = (fixture.id, with_semantic)
    if key not in _DBT_CACHE:
        suffix = "sem" if with_semantic else "base"
        root = tmp_path_factory.mktemp(f"dbt-{fixture.id[:12]}-{suffix}")
        _write_dbt_project(root, fixture, with_semantic=with_semantic)
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
    if "bad option: --experimental-strip-types" in proc.stderr:
        # Node < 22.6 cannot import a TypeScript module. Fail rather than skip
        # under strict mode: silently losing the drift guard is how the mirror
        # would fall behind templates.ts unnoticed.
        _need(False, "node >= 22.6 (--experimental-strip-types)")
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
    """Guard the mirror's provenance: extracted from the library, none hand-added.

    The claim is that every gold graph came from `templates.ts` and nothing was
    written into the mirror by hand. That is a statement about *provenance*, and
    it is checked by comparing the two sets — a graph in the mirror with no
    template behind it fails here whatever the totals are.

    It previously also asserted `len(GOLD_IDS) == 5`, which was a restatement of
    how many templates happened to exist rather than a property of anything.
    Adding a sixth reference model to the library failed this test while every
    emitter passed against it, which is the wrong way round: the count was the
    only thing that objected, and it objected to the library growing. Read the
    expected set off `templates.ts` instead, so the guard tracks the source it
    exists to protect.
    """
    assert _TEMPLATES_TS.is_file()
    index = json.loads((_GOLD_DIR / "index.json").read_text(encoding="utf-8"))
    assert set(index) == set(GOLD_IDS)

    declared = set(
        re.findall(
            r"^\s*id: '([a-z0-9-]+)',",
            _TEMPLATES_TS.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    assert declared, "fixture sanity: no template ids parsed out of templates.ts"
    assert set(GOLD_IDS) == declared, (
        f"the gold mirror and the Requirements Library disagree: "
        f"mirror-only={sorted(set(GOLD_IDS) - declared)}, "
        f"library-only={sorted(declared - set(GOLD_IDS))}"
    )


_EXPORT_PANEL = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "editor" / "ExportPanel.tsx"
)


def test_export_ui_offers_exactly_the_dialects_the_backend_supports() -> None:
    """The UI's dialect list must match the backend's, certification included.

    Finding M12. The export panel offered five dialects while the backend
    accepted seven: `redshift` was **certified and unreachable**, and
    `clickhouse` was **preview and offered without qualification**. The whole
    fidelity programme was therefore verifying a surface users could not fully
    reach, while users could reach a surface it had not verified.

    That is a gap between the harness and the product rather than a bug in
    either, which is exactly why neither caught it — the audit checked what the
    emitters produce, never what the UI lets you ask for. This test closes the
    seam so an eighth dialect cannot drift in on one side only.
    """
    source = _EXPORT_PANEL.read_text(encoding="utf-8")

    def declared(name: str) -> list[str]:
        match = re.search(rf"const {name} = \[(.*?)\];", source, re.S)
        assert match, f"{name} not found in ExportPanel.tsx"
        return re.findall(r"'([^']+)'", match.group(1))

    assert declared("CERTIFIED_DIALECTS") == list(CERTIFIED_DIALECTS), (
        "the UI's certified dialects differ from the ones this harness verifies"
    )
    assert declared("PREVIEW_DIALECTS") == list(PREVIEW_DIALECTS), (
        "the UI's preview dialects differ from the ones this harness labels"
    )

    # And both must agree with what the exporter will actually accept.
    from app.services.exporter_service import _SQLGLOT_DIALECTS

    backend = set(_SQLGLOT_DIALECTS) - {"postgresql"}  # an alias, not a dialect
    assert set(ALL_DIALECTS) == backend, (
        f"harness covers {sorted(ALL_DIALECTS)} but the exporter accepts "
        f"{sorted(backend)}"
    )


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


@pytest.mark.parametrize("gid", GOLD_IDS)
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


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_ddl_not_null_follows_declared_nullability(gid: str) -> None:
    """NOT NULL comes from `is_nullable`, not from the primary-key flag.

    Asserted against a mutated copy, for the same reason the ODCS `required`
    check is: on the graphs as authored, `is_nullable` is false exactly where
    `is_primary_key` is true, so emitting NOT NULL from either rule produces
    byte-identical DDL. `test_ddl_primary_key_columns_are_not_null` therefore
    passes under the wrong implementation — it asserts a consequence, not the
    property (register verification standard 9).

    One non-key column per entity is forced non-nullable here, which is the
    counterexample a correct model rarely contains.
    """
    model = GOLD[gid].model.model_copy(deep=True)
    forced: list[str] = []
    for entity in model.entities:
        for column in entity.columns:
            if not column.is_primary_key:
                column.is_nullable = False
                forced.append(column.name)
                break
    assert forced, "fixture sanity: no entity has a non-key column"

    ddl = exporter().generate_ddl(model, "postgres")
    for entity in model.entities:
        # Scoped to this table's own CREATE block. A column name is not unique
        # across a model — `plan_sk` is a nullable foreign key on the fact and
        # the non-nullable primary key of `dim_plan` — so an unscoped search
        # reads one table's constraint as another's.
        block = re.search(
            rf"CREATE TABLE {re.escape(entity.entity_name)} \((.*?)\n\);",
            ddl,
            re.S,
        )
        assert block, f"no CREATE TABLE emitted for {entity.entity_name}"
        for column in entity.columns:
            pattern = rf"^\s*{re.escape(column.name)}\s+\S.*$"
            line = re.search(pattern, block.group(1), re.M)
            assert line, f"{entity.entity_name}.{column.name} not emitted"
            emitted = "NOT NULL" in line.group(0).upper()
            assert emitted is (not column.is_nullable), (
                f"{entity.entity_name}.{column.name}: is_nullable="
                f"{column.is_nullable} but NOT NULL "
                f"{'was' if emitted else 'was not'} emitted — {line.group(0).strip()!r}"
            )


def test_ddl_order_defeats_both_plausible_wrong_orderings() -> None:
    """Emission order is a dependency sort, not declaration or alphabetical.

    The gold graphs catch alphabetical ordering only by accident — one of the
    five happens to have a child whose name sorts before its parent. Relying on
    that is fragile: rename an entity and the mutant survives. This model is
    adversarial to both plausible wrong implementations at once, so the
    discrimination is deliberate rather than incidental.

    `a_child` references `z_parent`, and is declared first. Declaration order
    is wrong. Alphabetical order is wrong. Only a dependency sort is right.
    """
    model = SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="a_child",
                entity_type="TABLE",  # type: ignore[arg-type]
                columns=[
                    ColumnSchema(name="a_child_id", data_type="INTEGER",
                                 is_primary_key=True),
                    ColumnSchema(name="z_parent_id", data_type="INTEGER",
                                 is_foreign_key=True),
                ],
            ),
            EntitySchema(
                entity_name="z_parent",
                entity_type="TABLE",  # type: ignore[arg-type]
                columns=[
                    ColumnSchema(name="z_parent_id", data_type="INTEGER",
                                 is_primary_key=True),
                ],
            ),
        ],
        relationships=[
            RelationshipSchema.model_validate(
                {"from": "a_child.z_parent_id", "to": "z_parent.z_parent_id",
                 "cardinality": "N:1"}
            )
        ],
    )
    ddl = exporter().generate_ddl(model, "postgres")
    order = re.findall(r"CREATE TABLE (\w+)", ddl)
    assert order == ["z_parent", "a_child"], (
        f"emitted {order}; the referenced table must be created first"
    )


@pytest.mark.parametrize("gid", gold_params(
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
# Every dbt gate below ran on the gold graphs alone, and no gold graph declares
# a quality rule — so no project dbt had ever been handed contained a
# dbt_expectations test or a `packages.yml` at all. Four defects (H11, H12, M14,
# M15) lived in that single blind spot and were found only when `dbt build`
# forced the synthetic fixture through. Parameterising over that fixture too is
# the structural repair; fixing the four instances is not.
_DBT_FIXTURES = {**GOLD, "quality-rules": SYNTHETIC["quality-rules"]}
_DBT_IDS = sorted(_DBT_FIXTURES)



def _need_dbt(fixture: Fixture) -> None:
    """Require dbt, and the package cache only when the project needs packages.

    The gold graphs declare no quality rules, so their projects depend on
    nothing and must not be gated on a cache they never read. Requiring it
    unconditionally would make five green tests fail for a reason that has
    nothing to do with what they assert.
    """
    _need(HAVE_DBT, "dbt-core")
    if "packages.yml" in exporter().generate_dbt_project(fixture.model):
        _need(HAVE_DBT_PACKAGES, _DBT_PACKAGES_HINT)


@pytest.mark.parametrize("gid", _DBT_IDS)
def test_dbt_parses(gid: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    """The generated dbt project must parse (harness-supplied sources aside)."""
    _need_dbt(_DBT_FIXTURES[gid])
    result = dbt_parse(_DBT_FIXTURES[gid], tmp_path_factory, with_semantic=False)
    assert result.success, result.error


@pytest.mark.parametrize("gid", _DBT_IDS)
def test_dbt_project_is_self_contained(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The exporter must declare the sources its own models reference (B14).

    The harness supplies only `dbt_project.yml` and `profiles.yml`, which are
    the consumer's to write. Everything else in the project is the exporter's
    output, so this passing means the artifact is genuinely self-contained
    rather than completed by scaffolding — the sources file the harness used to
    synthesise has been deleted, not merely left unused.
    """
    _need_dbt(_DBT_FIXTURES[gid])
    files = exporter().generate_dbt_project(_DBT_FIXTURES[gid].model)
    assert any(p.endswith("_sources.yml") for p in files), (
        "no sources declaration emitted; the project cannot stand alone"
    )
    result = dbt_parse(_DBT_FIXTURES[gid], tmp_path_factory, with_semantic=False)
    assert result.success, result.error


@pytest.mark.parametrize("gid", _DBT_IDS)
def test_dbt_no_deprecations(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A generated project must not rely on deprecated dbt syntax."""
    _need_dbt(_DBT_FIXTURES[gid])
    result = dbt_parse(_DBT_FIXTURES[gid], tmp_path_factory, with_semantic=False)
    deprecations = sorted(n for n in result.event_names() if "Deprecation" in n)
    assert not deprecations, f"dbt reported {deprecations}"


def test_dbt_declares_packages_yml(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """A project using dbt_expectations must declare it *and* dbt must accept it.

    Register correction: B11's criterion is that a project emitted with quality
    rules **resolves**, and the evidence named here asserted only that a file
    with the right name existed. dbt was never asked. That is the same class as
    B6 — a proof that a defective implementation also satisfies — and H12 lived
    inside the gap for a full release: the emitted packages.yml was malformed
    badly enough that dbt refuses to load the project, and this test was green.

    The resolution assertion now lives in `test_dbt_parses[quality-rules]`,
    which hands the file to dbt. What remains here is the narrower claim that
    the declaration is emitted at all (M7).
    """
    _need_dbt(SYNTHETIC["quality-rules"])
    files = exporter().generate_dbt_project(SYNTHETIC["quality-rules"].model)
    schema_yml = files["models/staging/schema.yml"]
    assert "dbt_expectations." in schema_yml, "fixture no longer exercises M7"
    assert any(p.endswith("packages.yml") for p in files), (
        "emits dbt_expectations tests but declares no packages.yml"
    )
    result = dbt_parse(
        SYNTHETIC["quality-rules"], tmp_path_factory, with_semantic=False
    )
    assert result.success, (
        f"packages.yml is emitted but dbt will not load the project: "
        f"{result.error}"
    )


def test_dbt_packages_match_the_verified_lock() -> None:
    """The declared package must be the one that resolved without deprecation.

    M15. `calogica/dbt_expectations` is redirected on dbt Hub, and resolving it
    raises PackageRedirectDeprecation twice — once for itself and once for its
    transitive `dbt_date`. Neither is visible offline: the deprecation fires
    against the registry, so no command this harness can run would ever see it.

    The enforcement therefore lives in `scripts/refresh_dbt_packages.py`, which
    resolves the exporter's own packages.yml over the network and **fails** on
    any deprecation. `package-lock.yml` is the artifact that run produced. This
    test asserts the emitter still names what that verified run resolved, which
    is what makes the committed lock evidence rather than decoration — the same
    relationship `requirements.lock` has to the environment it describes.
    """
    lock = yaml.safe_load(_DBT_LOCK_FIXTURE.read_text(encoding="utf-8"))
    resolved = {entry["package"] for entry in lock["packages"]}
    emitted = yaml.safe_load(
        exporter().generate_dbt_project(SYNTHETIC["quality-rules"].model)[
            "packages.yml"
        ]
    )
    declared = {entry["package"] for entry in emitted["packages"]}
    # A subset assertion is vacuously true on an empty set, which would make
    # this pass hardest exactly when the exporter has stopped declaring
    # anything at all.
    assert declared, "packages.yml declares no packages"
    assert declared <= resolved, (
        f"packages.yml declares {sorted(declared - resolved)}, which the "
        f"verified resolution in package-lock.yml does not contain. Re-run "
        f"scripts/refresh_dbt_packages.py — it fails on a deprecated package, "
        f"so a passing run is the evidence this assertion stands on."
    )


def test_dbt_accepted_values_agree_with_a_declared_check() -> None:
    """An emitted accepted_values test must not contradict the model's CHECK.

    Asserted as a set relation against the declared literals rather than
    against a specific list, so it states the property — the exported contract
    agrees with the model — rather than restating the fix.
    """
    fixture = SYNTHETIC["quality-rules"]
    files = exporter().generate_dbt_project(fixture.model)
    schema = yaml.safe_load(files["models/staging/schema.yml"])
    by_column = {
        col["name"]: col
        for model in schema["models"]
        for col in model.get("columns", [])
    }

    checked = 0
    for entity in fixture.model.entities:
        for column in entity.columns:
            declared = re.findall(r"'([^']*)'", column.check_expression or "")
            if not declared or " IN " not in (column.check_expression or "").upper():
                continue
            emitted = [
                test["accepted_values"]["arguments"]["values"]
                for test in by_column.get(column.name, {}).get("data_tests", [])
                if isinstance(test, dict) and "accepted_values" in test
            ]
            if not emitted:
                continue
            checked += 1
            assert set(emitted[0]) <= set(declared), (
                f"{column.name}: the exported dbt test accepts {emitted[0]} but "
                f"the model declares only {declared}. The contract and the "
                f"model disagree about the same column."
            )
    assert checked, "fixture no longer exercises H11"


def test_dbt_build_succeeds_on_generated_seed_data(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """B13, and the distance between "our exports parse" and "our exports run".

    `dbt parse` proves a project resolves. This executes it: the seed rows the
    product generates are loaded into DuckDB, every model the product exports is
    built against them, and every test the product exports is run.

    It is the first gate that can see a **cross-artifact** defect. Every other
    check in this file asks whether one artifact satisfies its own consumer, and
    both halves of H11 passed that bar individually — the seed was valid against
    the model, the dbt contract was valid dbt. They disagreed with each other,
    and nothing that examines one artifact at a time can notice.
    """
    _need_dbt(SYNTHETIC["quality-rules"])
    result = dbt_build(SYNTHETIC["quality-rules"], tmp_path_factory)
    failures = [
        msg for name, msg in result.events
        if name in ("LogTestResult", "LogModelResult") and " ERROR " not in msg
        and ("FAIL" in msg or "ERROR" in msg)
    ]
    assert result.success, (
        f"dbt build failed on the product's own fixtures: {result.error} "
        f"{failures[:4]}"
    )


# ===========================================================================
# 3. MetricFlow
# ===========================================================================
def _metricflow_doc(fixture: Fixture) -> dict[str, Any]:
    files = exporter().export_semantic_layer(fixture.model, "metricflow")
    return yaml.safe_load(files["semantic_models.yml"])


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_parses_in_dbt(
    gid: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The headline assertion: dbt accepts the emitted semantic layer."""
    _need(HAVE_DBT, "dbt-core")
    result = dbt_parse(GOLD[gid], tmp_path_factory, with_semantic=True)
    detail = "; ".join(result.messages("SemanticValidationFailure"))[:600]
    assert result.success, f"{result.error} {detail}"


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_metrics_have_label(gid: str) -> None:
    doc = _metricflow_doc(GOLD[gid])
    missing = [m["name"] for m in doc.get("metrics", []) if not m.get("label")]
    assert not missing, f"metrics without a label: {missing}"


@pytest.mark.parametrize("gid", GOLD_IDS)
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


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_agg_vocabulary_is_valid(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        for measure in semantic_model.get("measures", []):
            assert measure["agg"] in _METRICFLOW_AGGREGATIONS, (
                f"{semantic_model['name']}.{measure['name']} uses "
                f"agg={measure['agg']!r}"
            )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_declares_agg_time_dimension(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        if not semantic_model.get("measures"):
            continue
        agg_time = semantic_model.get("defaults", {}).get("agg_time_dimension")
        assert agg_time, (
            f"semantic model '{semantic_model['name']}' declares measures but "
            f"no defaults.agg_time_dimension"
        )


@pytest.mark.parametrize("gid", GOLD_IDS)
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


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_names_avoid_reserved_granularity(gid: str) -> None:
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        for block in ("entities", "dimensions", "measures"):
            for item in semantic_model.get(block, []):
                assert item["name"].lower() not in _RESERVED_GRANULARITIES, (
                    f"{semantic_model['name']}.{item['name']} is a reserved "
                    f"time-granularity keyword"
                )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_metricflow_measures_require_an_aggregation_time_axis(gid: str) -> None:
    """A semantic model with no `agg_time_column` declares no measures.

    Ruled behaviour, asserted so the rule is verifiable rather than incidental.
    Six of the fifteen reference entities have no temporal column and cannot
    acquire one honestly, so they are dimension-only rather than being given an
    invented time axis.

    The inverse is asserted in the same place, and it is the more fragile half:
    a model that *does* declare measures must carry the default, and the default
    must name a dimension that exists in the emitted block. Reserved-granularity
    names are renamed (`month` -> `month_dim`), so a default built from the raw
    column would point at a dimension that no longer exists — one fix silently
    undoing another inside the same emitter.
    """
    for semantic_model in _metricflow_doc(GOLD[gid]).get("semantic_models", []):
        default = semantic_model.get("defaults", {}).get("agg_time_dimension")
        measures = semantic_model.get("measures", [])
        if default is None:
            assert not measures, (
                f"'{semantic_model['name']}' has no aggregation time axis but "
                f"declares measures {[m['name'] for m in measures]}"
            )
            continue
        emitted = {d["name"] for d in semantic_model.get("dimensions", [])}
        assert default in emitted, (
            f"'{semantic_model['name']}' aggregates over {default!r}, which is "
            f"not among its dimensions {sorted(emitted)} — a renamed dimension "
            f"orphaned by its own default"
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


@pytest.mark.parametrize("gid", GOLD_IDS)
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
# 5. LookML — PREVIEW
#
# LookML is Preview, not certified. It is proprietary, no offline parser
# exists, so it is permanently unverifiable here (audit §4.5 records it as
# UNVERIFIED-by-toolchain), and the install base does not justify repair
# effort. The emitter stays behind a Preview label; these structural
# assertions are excluded from the Sprint 3 burn-down.
# ===========================================================================
@pytest.mark.preview
@pytest.mark.parametrize("gid", gold_params({
    gid: "M3: LookML excludes the primary key from measures but not foreign "
         "keys, so SUM() over an FK is emitted. Preview — not scheduled."
    # Every graph whose foreign keys are numeric. `banking-datavault` uses
    # CHAR hash keys and `marketing-attribution` is a single-table OBT, so
    # neither exhibits it. `aml-financial-crime` is a Kimball star with
    # INTEGER surrogate keys and exhibits it exactly as the other stars do.
    for gid in (
        "saas-subscription",
        "ecommerce-orders",
        "healthcare-ehr",
        "aml-financial-crime",
    )
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


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_odcs_apiversion_is_current(gid: str) -> None:
    assert _odcs(GOLD[gid])["apiVersion"] == ODCS_API_VERSION


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_odcs_conforms_to_v3_fundamentals(gid: str) -> None:
    doc = _odcs(GOLD[gid])
    assert doc.get("kind") == "DataContract"
    missing = [
        key
        for key in ("apiVersion", "kind", "id", "version", "status")
        if key not in doc
    ]
    assert not missing, f"ODCS v3.1.0 requires top-level {missing}"
    assert "info" not in doc, (
        "`info:` is a Data Contract Specification key, not ODCS v3"
    )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_odcs_required_reflects_nullability(gid: str) -> None:
    """`required` must derive from declared nullability, not from the PK flag.

    Asserted against a *mutated* copy in which one non-key column per entity is
    marked non-nullable, because on the gold graphs as authored the two rules
    are indistinguishable: with ``is_nullable`` defaulting to ``True`` and
    primary keys forced ``False``, ``not is_nullable`` and ``is_primary_key``
    agree on every column. A test that cannot tell the correct implementation
    from the current one would go green the moment Sprint 2 added the field,
    against an emitter that still never read it — passing for the wrong reason.
    See PROJECT_STATE_REPORT.md correction C7.
    """
    if "is_nullable" not in ColumnSchema.model_fields:
        pytest.fail(
            "ColumnSchema cannot express nullability, so `required` cannot be "
            "derived from it (Sprint 2, H4)"
        )

    fixture = GOLD[gid]
    model = fixture.model.model_copy(deep=True)
    # One non-key column per entity forced non-nullable: the counterexample the
    # authored graphs do not contain.
    discriminating: list[str] = []
    for entity in model.entities:
        for column in entity.columns:
            if not column.is_primary_key:
                column.is_nullable = False
                discriminating.append(f"{entity.entity_name}.{column.name}")
                break
    assert discriminating, "fixture sanity: no entity has a non-key column"

    columns = {
        (e.entity_name, c.name): c for e in model.entities for c in e.columns
    }
    contract = yaml.safe_load(
        exporter().export_data_contract(model, "odcs", fixture.dataset_name)[
            "datacontract.yaml"
        ]
    )
    for table in contract["schema"]:
        for prop in table["properties"]:
            column = columns[(table["name"], prop["name"])]
            expected = not column.is_nullable
            assert prop["required"] is expected, (
                f"{table['name']}.{prop['name']}: required={prop['required']} "
                f"but is_nullable={column.is_nullable} — `required` is "
                f"restating is_primary_key ({column.is_primary_key})"
            )


def test_odcs_quality_entries_use_v3_vocabulary() -> None:
    """Quality blocks must speak ODCS, not an invented dialect.

    Spec: https://github.com/bitol-io/open-data-contract-standard/blob/main/docs/data-quality.md
    Confirmed via context7 on 2026-08-11. A library rule carries `metric` and a
    `mustBe*` comparator; a SQL rule carries `type: sql` and `query`. There is
    no `rule` key at any level.
    """
    fixture = SYNTHETIC["quality-rules"]
    contract = yaml.safe_load(
        exporter().export_data_contract(fixture.model, "odcs", fixture.dataset_name)[
            "datacontract.yaml"
        ]
    )
    entries = [
        (table["name"], prop["name"], entry)
        for table in contract["schema"]
        for prop in table["properties"]
        for entry in prop.get("quality", [])
    ]
    assert entries, "fixture no longer exercises H10"

    offending: list[str] = []
    for table, prop, entry in entries:
        where = f"{table}.{prop}"
        if "rule" in entry:
            offending.append(f"{where}: 'rule' is not an ODCS key ({entry})")
            continue
        kind = entry.get("type", "library")
        if kind == "sql":
            if "query" not in entry:
                offending.append(f"{where}: a sql rule needs a query")
        elif "metric" not in entry:
            offending.append(f"{where}: a library rule needs a metric ({entry})")
        if not any(k == "mustBe" or k.startswith("mustBe") for k in entry):
            offending.append(f"{where}: no mustBe* comparator ({entry})")
    assert not offending, offending


def test_odcs_carries_the_meaning_of_each_declared_constraint() -> None:
    """Every declared constraint reaches the contract with its meaning intact.

    The vocabulary check above asks whether the document speaks ODCS. This asks
    whether it says the right thing — the distinction the H10 ruling turned on,
    because a contract that is valid and wrong is worse than one that is
    invalid. An emitter that dropped every bound and emitted a syntactically
    perfect `nullValues` entry instead would pass the vocabulary test outright.

    Where each constraint belongs, verified against Bitol's `schema.md` and
    `data-quality.md` via context7 on 2026-08-11:

    * a **numeric range** is a bound on the domain — `logicalTypeOptions`
      `minimum`/`maximum`. It is deliberately *not* a quality entry: the
      documented `invalidValues` arguments are `validValues` and `pattern`, and
      there is no argument for a numeric bound. Inventing one would produce a
      document that validates and communicates nothing.
    * a **regex** is documented in both places, so it appears in both: as
      `logicalTypeOptions.pattern` (the domain) and as an `invalidValues`
      quality entry with `mustBe: 0` (the measured assertion).
    * an **enumerated CHECK** is `invalidValues` with `arguments.validValues`.
    """
    fixture = SYNTHETIC["quality-rules"]
    contract = yaml.safe_load(
        exporter().export_data_contract(fixture.model, "odcs", fixture.dataset_name)[
            "datacontract.yaml"
        ]
    )
    props = {
        (table["name"], prop["name"]): prop
        for table in contract["schema"]
        for prop in table["properties"]
    }

    checked = {"range": 0, "regex": 0, "enum": 0}
    missing: list[str] = []
    for entity in fixture.model.entities:
        for column in entity.columns:
            prop = props[(entity.entity_name, column.name)]
            options = prop.get("logicalTypeOptions", {})
            arguments = [
                entry.get("arguments", {})
                for entry in prop.get("quality", [])
                if entry.get("metric") == "invalidValues"
                and entry.get("mustBe") == 0
            ]
            where = f"{entity.entity_name}.{column.name}"

            if column.min_value is not None:
                checked["range"] += 1
                if options.get("minimum") != column.min_value:
                    missing.append(
                        f"{where}: declares min {column.min_value}, contract "
                        f"says {options.get('minimum')!r}"
                    )
            if column.max_value is not None:
                if options.get("maximum") != column.max_value:
                    missing.append(
                        f"{where}: declares max {column.max_value}, contract "
                        f"says {options.get('maximum')!r}"
                    )
            if column.regex_pattern:
                checked["regex"] += 1
                if options.get("pattern") != column.regex_pattern:
                    missing.append(f"{where}: pattern absent from the domain")
                if not any(
                    a.get("pattern") == column.regex_pattern for a in arguments
                ):
                    missing.append(f"{where}: pattern is asserted by no rule")
            declared = re.findall(r"'([^']*)'", column.check_expression or "")
            if declared and " IN " in (column.check_expression or "").upper():
                checked["enum"] += 1
                if not any(
                    a.get("validValues") == declared for a in arguments
                ):
                    missing.append(
                        f"{where}: CHECK allows {declared}, contract asserts "
                        f"{[a.get('validValues') for a in arguments]}"
                    )

    assert not missing, missing
    unexercised = sorted(kind for kind, n in checked.items() if not n)
    assert not unexercised, (
        f"the fixture declares no {unexercised}, so that branch asserts nothing"
    )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_odcs_declares_foreign_keys_as_relationships(gid: str) -> None:
    """A column-level FK target reaches the contract (register C7).

    ODCS v3.1.0 expresses this at property level as ``relationships: [{to}]``
    with ``from`` implicit; ``type: foreignKey`` is the schema-level construct
    and needs explicit ``from`` and ``to``. Correction C7-a — C3 named the
    property-level construct wrongly, and Sprint 2's decision to keep
    ``ColumnSchema.references`` rested on that name.

    The gold graphs carry no ``references`` values, so this asserts the
    round-trip on a model that does: absence here would otherwise look like
    conformance.
    """
    fixture = GOLD[gid]
    model = fixture.model.model_copy(deep=True)

    # Give each FK column the qualified target its relationship already implies.
    expected: dict[tuple[str, str], str] = {}
    by_entity = {e.entity_name: e for e in model.entities}
    for rel in model.relationships:
        child, child_col = rel.from_ref.split(".", 1)
        if not child_col or child not in by_entity:
            continue
        column = next(
            (c for c in by_entity[child].columns if c.name == child_col), None
        )
        if column is None:
            continue
        column.references = rel.to_ref
        expected[(child, child_col)] = rel.to_ref
    if not expected:
        pytest.skip("single-entity model declares no foreign keys")

    contract = yaml.safe_load(
        exporter().export_data_contract(model, "odcs", fixture.dataset_name)[
            "datacontract.yaml"
        ]
    )
    for table in contract["schema"]:
        for prop in table["properties"]:
            target = expected.get((table["name"], prop["name"]))
            if target is None:
                assert "relationships" not in prop, (
                    f"{table['name']}.{prop['name']} claims a relationship it "
                    f"does not have"
                )
                continue
            assert prop.get("relationships") == [{"to": target}], (
                f"{table['name']}.{prop['name']} should declare "
                f"relationships: [{{to: {target}}}], got "
                f"{prop.get('relationships')!r}"
            )
            assert "foreignKey" not in prop, (
                "foreignKey is the schema-level construct, not a property key"
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


def _persisted(fixture: Fixture, *, gap_after: int = 2) -> Fixture:
    """A copy whose columns carry stable ids, as a saved model's would.

    The gold graphs are loaded straight from JSON and never persisted, so every
    ``stable_id`` is ``None`` — and a tag-stability test over them would prove
    nothing about a field the emitter only reads when it is set (register
    verification standard 8).

    Ids are assigned **with a gap**, which is the whole point. A model that has
    ever had a column deleted has non-contiguous ids, and that is precisely the
    case the plausible wrong implementation gets wrong: sorting the columns by
    ``stable_id`` and then numbering by loop index looks correct, is stable
    under reorder, and quietly re-compacts the gap — reissuing a tag a deployed
    consumer still holds.
    """
    model = fixture.model.model_copy(deep=True)
    for entity in model.entities:
        next_id = 1
        for index, column in enumerate(entity.columns):
            column.stable_id = next_id
            # Simulate one previously-deleted column part-way along.
            next_id += 2 if index == gap_after else 1
    return Fixture(fixture.id, model, fixture.dataset_name, fixture.raw)


def _proto_name(fixture: Fixture) -> str:
    return f"{ExporterService._safe_identifier(fixture.dataset_name)}.proto"


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_protobuf_tags_stable_on_insert(gid: str) -> None:
    """Inserting a column must not move any existing field tag.

    The criterion the whole ``stable_id`` design exists for. A tag is a wire
    contract: a deployed consumer decodes field 3 as whatever field 3 meant
    when its copy of the schema was generated.
    """
    fixture = _persisted(GOLD[gid])
    before = _proto_files(fixture)[_proto_name(fixture)]

    mutated = fixture.model.model_copy(deep=True)
    target = mutated.entities[0]
    highest = max(c.stable_id or 0 for c in target.columns)
    target.columns.insert(
        1,
        ColumnSchema(
            name="inserted_column",
            data_type="VARCHAR(80)",
            # A newly allocated id: past the high-water mark, never reused.
            stable_id=highest + 1,
        ),
    )
    after = _proto_files(
        Fixture(fixture.id, mutated, fixture.dataset_name, fixture.raw)
    )[_proto_name(fixture)]

    message = ExporterService._to_pascal_case(target.entity_name)
    original = _proto_tags(before, message)
    updated = _proto_tags(after, message)
    moved = {
        name: (tag, updated.get(name))
        for name, tag in original.items() if updated.get(name) != tag
    }
    assert not moved, (
        f"field tags moved after an insertion: {moved}. A deployed consumer "
        f"would misparse every one of them."
    )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_protobuf_tags_are_the_stable_ids(gid: str) -> None:
    """Tags are the identities themselves, gaps included, not a renumbering."""
    fixture = _persisted(GOLD[gid])
    proto = _proto_files(fixture)[_proto_name(fixture)]
    for entity in fixture.model.entities:
        message = ExporterService._to_pascal_case(entity.entity_name)
        emitted = _proto_tags(proto, message)
        expected = {c.name: c.stable_id for c in entity.columns}
        assert emitted == expected, (
            f"{message}: tags {emitted} are not the stable ids {expected} — a "
            f"gap has been compacted, which reissues a retired tag"
        )


@pytest.mark.parametrize("gid", GOLD_IDS)
def test_protobuf_decimal_is_not_double(gid: str) -> None:
    """Exact numerics must not become binary floats.

    A NUMERIC(18,2) ledger balance is exact by definition. Avro emits a decimal
    logical type with precision and scale from the same column, so mapping the
    same value to `double` made the two contracts disagree about it.
    """
    fixture = GOLD[gid]
    proto = _proto_files(fixture)[_proto_name(fixture)]
    offending = [
        f"{e.entity_name}.{c.name}({c.data_type})"
        for e in fixture.model.entities for c in e.columns
        if any(t in c.data_type.upper() for t in ("NUMERIC", "DECIMAL", "NUMBER"))
        and re.search(rf"^\s*double {re.escape(c.name)} = \d+;", proto, re.M)
    ]
    assert not offending, f"fixed-point columns emitted as double: {offending}"


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


# Seed constraints are exercised across the gold graphs *and* the synthetic
# constraints fixture. Parameterising over gold alone is register standard 8:
# no gold graph declares a range, a pattern, uniqueness, a default or a check,
# so every one of those rules would have been asserted against data that never
# contains it.
_SEED_FIXTURES = {**GOLD, "quality-rules": SYNTHETIC["quality-rules"]}
_SEED_IDS = sorted(_SEED_FIXTURES)


def test_seed_fixtures_exercise_every_declared_rule() -> None:
    """Standard 8: no seed rule may be asserted against data lacking it.

    Every test below walks the columns and `continue`s past any that does not
    declare the rule it checks, so a fixture edit that drops the only column
    carrying a constraint turns a real assertion into a green no-op — silently,
    and in the direction that looks like success. This is the one test in the
    group that fails when the *fixtures* regress rather than the generator.
    """
    columns = [
        col
        for fixture in _SEED_FIXTURES.values()
        for entity in fixture.model.entities
        for col in entity.columns
    ]
    exercised = {
        "declared length": any(_declared_length(c.data_type) for c in columns),
        "range": any(
            c.min_value is not None or c.max_value is not None for c in columns
        ),
        "regex": any(c.regex_pattern for c in columns),
        "precision/scale": any(
            re.search(r"\(\s*\d+\s*,\s*\d+\s*\)", c.data_type)
            and "NUMERIC" in c.data_type.upper()
            for c in columns
        ),
        "enumerated check": any(
            c.check_expression and " IN " in c.check_expression.upper()
            for c in columns
        ),
        "uniqueness": any(c.is_unique and not c.is_primary_key for c in columns),
        "non-nullability": any(
            not c.is_nullable and not c.is_primary_key for c in columns
        ),
        "default": any(c.default_value for c in columns),
    }
    unexercised = sorted(rule for rule, seen in exercised.items() if not seen)
    assert not unexercised, (
        f"no seed fixture declares: {unexercised}. The tests for these rules "
        f"still pass, and they mean nothing."
    )


@pytest.mark.parametrize("gid", _SEED_IDS)
def test_seed_respects_declared_length(gid: str) -> None:
    fixture = _SEED_FIXTURES[gid]
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


def test_seed_respects_declared_precision_and_scale() -> None:
    """Generated numerics must fit the declared NUMERIC(p, s)."""
    fixture = SYNTHETIC["quality-rules"]
    rows = _seed_rows(fixture)
    violations: list[str] = []
    for entity in fixture.model.entities:
        for column in entity.columns:
            match = re.search(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", column.data_type)
            if not match or "NUMERIC" not in column.data_type.upper():
                continue
            precision, scale = int(match.group(1)), int(match.group(2))
            for row in rows.get(entity.entity_name, []):
                digits = row[column.name].lstrip("-").replace(".", "")
                whole, _, frac = row[column.name].lstrip("-").partition(".")
                if len(digits) > precision or len(frac) > scale:
                    violations.append(
                        f"{column.name}={row[column.name]} against "
                        f"{column.data_type}"
                    )
                    break
    assert not violations, f"values overflow their declared scale: {violations}"


def test_seed_satisfies_an_enumerated_check_expression() -> None:
    """A simple `col IN (...)` check must constrain the generated values.

    Scoped deliberately. A value generator cannot evaluate an arbitrary SQL
    predicate, and pretending otherwise would be untested handling. An
    enumerated IN-list is the case that actually occurs, is unambiguous to
    parse, and is precisely where the generator already guesses — it has a
    hard-coded status vocabulary that the model may contradict.
    """
    fixture = SYNTHETIC["quality-rules"]
    rows = _seed_rows(fixture)
    violations: list[str] = []
    for entity in fixture.model.entities:
        for column in entity.columns:
            if not column.check_expression:
                continue
            allowed = re.findall(r"'([^']*)'", column.check_expression)
            if " IN " not in column.check_expression.upper() or not allowed:
                continue  # not an enumeration; out of scope by design
            for row in rows.get(entity.entity_name, []):
                if row[column.name] not in allowed:
                    violations.append(
                        f"{column.name}={row[column.name]!r} not in {allowed}"
                    )
                    break
    assert not violations, f"seed violates a declared CHECK: {violations}"


@pytest.mark.parametrize("gid", _SEED_IDS)
def test_seed_values_are_unique_where_declared(gid: str) -> None:
    """A column declared UNIQUE must not repeat a value in the seed."""
    fixture = _SEED_FIXTURES[gid]
    rows = _seed_rows(fixture)
    for entity in fixture.model.entities:
        for column in entity.columns:
            if not (column.is_unique or column.is_primary_key):
                continue
            values = [r[column.name] for r in rows.get(entity.entity_name, [])]
            assert len(values) == len(set(values)), (
                f"{entity.entity_name}.{column.name} is declared unique but "
                f"the seed repeats a value"
            )


@pytest.mark.parametrize("gid", _SEED_IDS)
def test_seed_never_nulls_a_non_nullable_column(gid: str) -> None:
    """No NULL where the model declares the column mandatory."""
    fixture = _SEED_FIXTURES[gid]
    rows = _seed_rows(fixture)
    for entity in fixture.model.entities:
        for column in entity.columns:
            if column.is_nullable:
                continue
            for row in rows.get(entity.entity_name, []):
                assert row[column.name] not in ("", "NULL"), (
                    f"{entity.entity_name}.{column.name} is NOT NULL but the "
                    f"seed emitted {row[column.name]!r}"
                )


def test_default_and_check_reach_an_emitter() -> None:
    """A declared DEFAULT and CHECK must reach a consuming emitter (M13).

    Asserted by meaning, not by substring. The first version of this test
    searched every artifact for the literal `check_expression` text, and that
    is the wrong question: ODCS expresses an enumerated CHECK as an
    `invalidValues` rule carrying `validValues`, which is the constraint's
    meaning rendered in the standard's own vocabulary. A test demanding the raw
    SQL string back would fail the correct emitter and pass one that pasted the
    predicate somewhere harmless.

    `default_value` is emitted verbatim because SQL `DEFAULT` takes the literal
    the model authored — there the text *is* the meaning.
    """
    fixture = SYNTHETIC["quality-rules"]
    svc = exporter()
    ddl = svc.generate_ddl(fixture.model, "postgres")
    contract = yaml.safe_load(
        svc.export_data_contract(fixture.model, "odcs", fixture.dataset_name)[
            "datacontract.yaml"
        ]
    )
    dbt_schema = yaml.safe_load(
        svc.generate_dbt_project(fixture.model)["models/staging/schema.yml"]
    )
    quality_args = {
        (table["name"], prop["name"]): [
            entry.get("arguments", {}) for entry in prop.get("quality", [])
        ]
        for table in contract["schema"]
        for prop in table["properties"]
    }
    dbt_values = {
        col["name"]: test["accepted_values"]["arguments"]["values"]
        for model in dbt_schema["models"]
        for col in model.get("columns", [])
        for test in col.get("data_tests", [])
        if isinstance(test, dict) and "accepted_values" in test
    }

    checked = {"default": 0, "check": 0}
    missing: list[str] = []
    for entity in fixture.model.entities:
        for col in entity.columns:
            where = f"{entity.entity_name}.{col.name}"
            if col.default_value:
                checked["default"] += 1
                if f"DEFAULT {col.default_value}" not in ddl:
                    missing.append(f"{where}: DEFAULT reaches no DDL")
            allowed = re.findall(r"'([^']*)'", col.check_expression or "")
            if allowed and " IN " in (col.check_expression or "").upper():
                checked["check"] += 1
                args = quality_args.get((entity.entity_name, col.name), [])
                if not any(a.get("validValues") == allowed for a in args):
                    missing.append(f"{where}: CHECK reaches no contract rule")
                if dbt_values.get(col.name) != allowed:
                    missing.append(f"{where}: CHECK reaches no dbt test")

    assert not missing, missing
    unexercised = sorted(kind for kind, n in checked.items() if not n)
    assert not unexercised, f"fixture no longer exercises M13: {unexercised}"


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
