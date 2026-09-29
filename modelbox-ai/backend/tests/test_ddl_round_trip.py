"""The round trip: import, save, reopen, export PostgreSQL DDL, re-import, reconcile.

For each certified fixture (Oracle HR, Oracle CO, Pagila, AdventureWorks) the
exported DDL is imported again and its tables, columns, primary keys, foreign
keys, CHECK constraints and descriptions are compared, table by table, with
the **original catalog manifest** — the counts read from the source
database's own catalog views, which neither the importer nor the exporter
wrote.

Every difference must be an export gap the exporter named, and every named
gap must account for a difference: the expected shortfall is computed from
the gaps, and it must equal the actual shortfall exactly. A gap cannot excuse
a loss it does not describe, and a loss cannot pass unnamed.

**Partitions are excluded.** A partition is metadata of its parent table
(Sprint 8 Step 2a): the model has no entity for it and the export no table,
so the manifest's partition rows (Pagila's 55 `payment_p*`) are left out of
the comparison, and the parents are compared as tables.

The save and reopen go through the real persistence path (GraphRepository,
then SynthesisEngine.get_model), so a loss in storage fails here too.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.metadata_store import Base, DataModel, Workspace
from app.schemas.data_model import SynthesizedModel
from app.services import ddl_export
from app.services.ddl_import import counter
from app.services.ddl_import.importer import import_ddl
from app.services.exporter_service import ExporterService
from app.services.graph_repository import GraphRepository
from app.services.synthesis_engine import SynthesisEngine
from tests._test_db import make_test_engine

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DDL = Path(__file__).resolve().parent / "fixtures" / "ddl"
CERTIFIED = [("oracle", "hr"), ("oracle", "co"), ("postgres", "pagila"), ("tsql", "adventureworks")]
COMPARED = ("columns", "primary_keys", "foreign_keys", "check_constraints",
            "table_descriptions", "column_descriptions")


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def _save_and_reopen(session: AsyncSession, model: SynthesizedModel, dialect: str) -> SynthesizedModel:
    workspace = Workspace(name="round trip")
    session.add(workspace)
    await session.flush()
    row = DataModel(workspace_id=workspace.workspace_id, title="round trip", target_dialect=dialect,
                    current_paradigm=str(model.paradigm))
    session.add(row)
    await session.flush()
    await GraphRepository(session).replace_graph(row.model_id, model.entities, model.relationships)
    await session.commit()
    reopened = await SynthesisEngine(session, None).get_model(row.model_id)  # type: ignore[arg-type]
    assert reopened is not None
    return SynthesizedModel(paradigm=reopened.paradigm, entities=reopened.entities,
                            relationships=reopened.relationships)


def _manifest_tables(dialect: str, stem: str) -> dict[str, dict[str, int]]:
    """The catalog's counts per table, partitions left out (see the module docstring)."""
    manifest = json.loads((DDL / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))
    return {t["name"].split(".")[-1]: {k: int(t[k]) for k in COMPARED}
            for t in manifest["tables"] if not t.get("partition_of")}


def _expected_shortfall(model: SynthesizedModel, gaps: list[ddl_export.ExportGap]) -> Counter[tuple[str, str]]:
    """What the named gaps say the re-import will lack, by (table, kind)."""
    shortfall: Counter[tuple[str, str]] = Counter()
    by_name = {e.entity_name: e for e in model.entities}
    for gap in gaps:
        entity = by_name.get(gap.entity or "")
        if gap.kind == "computed_column" and entity is not None:
            column_name = gap.detail.split(" ", 1)[0]
            shortfall[(entity.entity_name, "columns")] += 1
            column = next(c for c in entity.columns if c.name == column_name)
            if column.description:
                shortfall[(entity.entity_name, "column_descriptions")] += 1
        elif gap.kind in ("foreign_key", "unresolved_relationship"):
            shortfall[(gap.entity or "", "foreign_keys")] += 1
        elif gap.kind == "check_constraint":
            shortfall[(gap.entity or "", "check_constraints")] += 1
        elif gap.kind == "primary_key":
            shortfall[(gap.entity or "", "primary_keys")] += 1
        elif gap.kind == "description":
            raise AssertionError(f"PostgreSQL has COMMENT ON; no description gap is expected: {gap}")
        # data_type and unique_constraint gaps change no compared count.
    return shortfall


async def _round_trip(session: AsyncSession, dialect: str, stem: str) -> tuple[
        dict[str, dict[str, int]], dict[str, dict[str, int]], list[ddl_export.ExportGap], SynthesizedModel]:
    imported = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert imported.status == "reconciled" and imported.model is not None
    reopened = await _save_and_reopen(session, imported.model, dialect)
    export = ExporterService(source_dialect=dialect).generate_ddl_export(reopened, "postgres")
    again = import_ddl(export.sql.encode(), "postgres", f"{stem}.postgres.sql")
    assert again.report["failures"] == [], again.report["failures"][:3]
    assert again.status == "reconciled", again.report["reconciliation"]["gaps"][:3]
    per_table = counter.count(export.sql, "postgres")
    got = {name: {k: t.counts[k] for k in COMPARED} for name, t in per_table.items()}
    return _manifest_tables(dialect, stem), got, export.gaps, reopened


def _differences(catalog: dict[str, dict[str, int]], got: dict[str, dict[str, int]]) -> Counter[tuple[str, str]]:
    assert set(got) == set(catalog), f"tables differ: {sorted(set(catalog) ^ set(got))}"
    out: Counter[tuple[str, str]] = Counter()
    for table, counts in catalog.items():
        for kind in COMPARED:
            if counts[kind] != got[table][kind]:
                out[(table, kind)] = counts[kind] - got[table][kind]
    return out


@pytest.mark.parametrize(("dialect", "stem"), CERTIFIED, ids=[s for _, s in CERTIFIED])
async def test_the_round_trip_matches_the_catalog_or_names_each_difference(
    session: AsyncSession, dialect: str, stem: str
) -> None:
    catalog, got, gaps, reopened = await _round_trip(session, dialect, stem)
    assert _differences(catalog, got) == _expected_shortfall(reopened, gaps)


async def test_the_genuine_oracle_and_postgres_fixtures_round_trip_with_no_difference(session: AsyncSession) -> None:
    """HR and CO export with no gap at all. Pagila's catalog counts match
    exactly too, but its export names two kinds of gap that PostgreSQL itself
    found (Step 4a, test_ddl_on_postgres): serial defaults calling sequences
    the model does not hold, and user-defined types it does not define."""
    for dialect, stem in CERTIFIED[:3]:
        catalog, got, gaps, _ = await _round_trip(session, dialect, stem)
        if stem == "pagila":
            kinds = Counter(g.kind for g in gaps)
            assert kinds == Counter({"default": 13, "data_type": 3}), kinds
            assert all("sequence" in g.detail for g in gaps if g.kind == "default")
            assert all("user-defined type" in g.detail for g in gaps if g.kind == "data_type")
        else:
            assert gaps == [], (stem, gaps[:3])
        assert got == catalog, stem


async def test_adventureworks_differs_only_by_its_ten_computed_columns(session: AsyncSession) -> None:
    """The one kind of loss in the four fixtures, stated by name: a computed
    column's expression is held in the import report, not the model, so the
    export has no definition to give it. Its description goes with it."""
    catalog, got, gaps, _ = await _round_trip(session, "tsql", "adventureworks")
    kinds = Counter(g.kind for g in gaps)
    assert kinds["computed_column"] == 10
    assert set(kinds) <= {"computed_column", "data_type"}
    differences = _differences(catalog, got)
    assert sum(v for (_, kind), v in differences.items() if kind == "columns") == 10
    assert {kind for _, kind in differences} <= {"columns", "column_descriptions"}


def test_partitions_are_excluded_from_the_round_trip() -> None:
    """Pagila's catalog has 55 partitions of payment; none is compared."""
    manifest = json.loads((DDL / "postgres" / "pagila.manifest.json").read_text(encoding="utf-8"))
    partitions = [t for t in manifest["tables"] if t.get("partition_of")]
    assert len(partitions) == 55
    assert not set(_manifest_tables("postgres", "pagila")) & {t["name"].split(".")[-1] for t in partitions}


# --- Negative controls: the round trip catches a silent loss ---------------------

async def test_negative_control_without_foreign_key_emission_the_round_trip_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ddl_export, "_foreign_key", lambda rel, entity_columns, gaps: None)
    catalog, got, gaps, reopened = await _round_trip(session, "oracle", "hr")
    differences = _differences(catalog, got)
    assert differences != _expected_shortfall(reopened, gaps)
    assert {kind for _, kind in differences} == {"foreign_keys"}


async def test_negative_control_without_description_emission_the_round_trip_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ddl_export, "_descriptions", lambda entity, emitted: [])
    catalog, got, gaps, reopened = await _round_trip(session, "oracle", "hr")
    differences = _differences(catalog, got)
    assert differences != _expected_shortfall(reopened, gaps)
    assert {kind for _, kind in differences} == {"table_descriptions", "column_descriptions"}
