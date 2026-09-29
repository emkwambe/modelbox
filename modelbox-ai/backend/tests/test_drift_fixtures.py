"""The drift report against genuinely drifted databases (Sprint 8 Step 5, item 7).

For Oracle HR, Pagila and AdventureWorks, the DDL Fixtures workflow applies a
committed ALTER script (``ddl_drift/<dialect>/changes/*.alter.sql``) to the
real database after exporting its baseline fixture, then exports it again:
``ddl_drift/<dialect>/<stem>.sql`` is the deployed schema. Each script has an
expected-drift manifest (``*.expected.json``) written from the script,
statement by statement, not from ModelBox's output.

Here the baseline fixture is imported and saved (the documented design), the
drifted one imported fresh (the deployed schema), and the report compared
with the manifest: **every expected drift is reported, none is invented, and
each has the class the manifest gives**; the possible-rename hints are
exactly the manifest's. Every numbered statement of each script is accounted
for by the manifest.

Negative controls: with one drift category suppressed in the comparison core,
and with one classification rule broken, the comparison fails.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.metadata_store import Base
from app.services import diff_engine, drift_report, drift_rules
from app.services.ddl_import.importer import import_ddl
from tests._test_db import make_test_engine
from tests.test_ddl_round_trip import DDL, _save_and_reopen

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DRIFT = Path(__file__).resolve().parent / "fixtures" / "ddl_drift"
FIXTURES = [("oracle", "hr"), ("postgres", "pagila"), ("tsql", "adventureworks")]


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = make_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


def _expected(dialect: str, stem: str) -> dict[str, Any]:
    return json.loads((DRIFT / dialect / "changes" / f"{stem}.expected.json").read_text(encoding="utf-8"))


def _key(drift: dict[str, Any]) -> tuple[str, str, str | None, tuple[str, ...]]:
    """What identifies a drift. A table has one primary key, so its change is
    identified by the table; the report lists the new key's columns besides."""
    columns = () if drift["kind"] == "primary_key_changed" else tuple(drift.get("columns") or ())
    return (drift["kind"], drift["table"], drift.get("column"), columns)


async def _report(session: AsyncSession, dialect: str, stem: str) -> dict[str, Any]:
    baseline = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    deployed = import_ddl((DRIFT / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert baseline.model is not None and deployed.model is not None
    design = await _save_and_reopen(session, baseline.model, dialect)
    return drift_report.build(
        design, deployed.model,  # type: ignore[arg-type]
        drift_report.Source("Design", stem, baseline.status, version=1),
        drift_report.Source("Deployed", f"{stem}.sql", deployed.status, imported_at="fixture"),
        dialect=dialect)


def _check(report: dict[str, Any], expected: dict[str, Any]) -> None:
    """Every expected drift reported, none invented, each classified as the manifest says."""
    got = {_key(d): d["class"] for d in report["drifts"]}
    want = {_key(d): d["class"] for d in expected["drifts"]}
    missing = sorted(set(want) - set(got))
    invented = sorted(set(got) - set(want))
    assert not missing and not invented, f"missing {missing}\ninvented {invented}"
    wrong = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    assert not wrong, f"misclassified (reported, expected): {wrong}"
    hints = {(h["table"], h["removed"], h["added"]) for h in report["possible_renames"]}
    assert hints == {(h["table"], h["removed"], h["added"]) for h in expected["possible_renames"]}


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
def test_every_alter_statement_is_in_its_manifest(dialect: str, stem: str) -> None:
    script = (DRIFT / dialect / "changes" / f"{stem}.alter.sql").read_text(encoding="utf-8")
    numbered = {int(n) for n in re.findall(r"^-- (\d+)\. ", script, re.MULTILINE)}
    assert numbered, "fixture sanity: the script numbers its statements"
    assert {d["statement"] for d in _expected(dialect, stem)["drifts"]} == numbered


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
async def test_the_report_finds_exactly_the_expected_drifts(session: AsyncSession, dialect: str, stem: str) -> None:
    report = await _report(session, dialect, stem)
    _check(report, _expected(dialect, stem))
    assert report["summary"]["total"] == len(_expected(dialect, stem)["drifts"])


@pytest.mark.parametrize(("dialect", "stem"), FIXTURES, ids=[s for _, s in FIXTURES])
async def test_a_baseline_against_itself_has_no_drift(session: AsyncSession, dialect: str, stem: str) -> None:
    """The saved design against a fresh import of the same file: nothing invented by the save."""
    baseline = import_ddl((DDL / dialect / f"{stem}.sql").read_bytes(), dialect, f"{stem}.sql")
    assert baseline.model is not None
    design = await _save_and_reopen(session, baseline.model, dialect)
    report = drift_report.build(design, baseline.model, drift_report.Source("Design", stem, baseline.status),
                                drift_report.Source("Deployed", stem, baseline.status), dialect=dialect)
    assert report["drifts"] == []


async def test_negative_control_a_suppressed_drift_category_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = diff_engine.compare

    def without_nullability(*args: Any, **kwargs: Any) -> list[diff_engine.Change]:
        return [c for c in real(*args, **kwargs) if c.kind != "nullability_changed"]

    monkeypatch.setattr(drift_report, "compare", without_nullability)
    report = await _report(session, "postgres", "pagila")
    with pytest.raises(AssertionError, match="missing"):
        _check(report, _expected("postgres", "pagila"))


async def test_negative_control_a_broken_classification_rule_fails(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tuple(r if r.id != "D7" else drift_rules.Rule("D7", r.text, drift_rules.NON_BREAKING, r.applies)
                   for r in drift_rules.RULES)
    monkeypatch.setattr(drift_rules, "RULES", broken)
    report = await _report(session, "oracle", "hr")
    with pytest.raises(AssertionError, match="misclassified"):
        _check(report, _expected("oracle", "hr"))


def test_the_drift_fixtures_are_genuine_tool_output() -> None:
    """Each drifted export carries its exporter's provenance and names its ALTER script."""
    for dialect, stem in FIXTURES:
        head = (DRIFT / dialect / f"{stem}.sql").read_text(encoding="utf-8").split("-- end of provenance")[0]
        assert "genuine tool output" in head, (dialect, stem)
        assert f"ddl_drift/{dialect}/changes/{stem}.alter.sql sha256 " in head, (dialect, stem)
        manifest = json.loads((DRIFT / dialect / f"{stem}.manifest.json").read_text(encoding="utf-8"))
        assert manifest["counts_from"].startswith("catalog views"), (dialect, stem)
