"""`compare_fixture.py` tells a regenerated fixture from an edited one.

`ddl-fixtures.yml` runs it after regenerating every DDL fixture, and it is the
only thing that makes "the committed fixture is what the tool produced" true.
Here it runs on copies of the committed fixtures: identical copies, and copies
differing only in the generation date and run, must pass; one edited
statement, one changed count, and a fixture missing on either side must each
fail.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ddl_fixtures" / "compare_fixture.py"
ORACLE = Path(__file__).resolve().parent / "fixtures" / "ddl" / "oracle"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compare_fixture", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    committed, regenerated = tmp_path / "committed", tmp_path / "regenerated"
    shutil.copytree(ORACLE, committed)
    shutil.copytree(ORACLE, regenerated)
    return committed, regenerated


def test_identical_fixtures_match(pair: tuple[Path, Path]) -> None:
    assert _load().compare(*pair) == []


def test_only_the_date_and_run_may_differ(pair: tuple[Path, Path]) -> None:
    _, regenerated = pair
    sql = regenerated / "hr.sql"
    lines = sql.read_text(encoding="utf-8").splitlines()
    lines = [
        "-- generated: 2099-01-01 by https://github.com/o/r/actions/runs/1"
        if line.startswith("-- generated: ") else line
        for line in lines
    ]
    sql.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = regenerated / "hr.manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.update(generated="2099-01-01", run="https://github.com/o/r/actions/runs/1")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _load().compare(*pair) == []


def test_negative_control_an_edited_statement_is_a_difference(pair: tuple[Path, Path]) -> None:
    committed, _ = pair
    sql = committed / "hr.sql"
    text = sql.read_text(encoding="utf-8")
    assert "STORAGE(INITIAL" in text
    sql.write_text(text.replace("STORAGE(INITIAL", "STORAGE( INITIAL", 1), encoding="utf-8")
    problems = _load().compare(*pair)
    assert len(problems) == 1 and problems[0].startswith("hr.sql: differs")


def test_negative_control_a_changed_count_is_a_difference(pair: tuple[Path, Path]) -> None:
    committed, _ = pair
    manifest = committed / "co.manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["counts"]["columns"] += 1
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _load().compare(*pair) == ["co.manifest.json: manifest differs"]


@pytest.mark.parametrize("side", ["committed", "regenerated"])
def test_negative_control_a_missing_fixture_is_a_difference(
    pair: tuple[Path, Path], side: str
) -> None:
    committed, regenerated = pair
    (committed if side == "committed" else regenerated).joinpath("co.sql").unlink()
    expected = (
        "co.sql: regenerated but not committed" if side == "committed"
        else "co.sql: committed but not regenerated"
    )
    assert _load().compare(*pair) == [expected]
