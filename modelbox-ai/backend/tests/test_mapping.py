"""Source-to-target mapping: completeness, drift, proposals and exports (Sprint 9 Step 3).

The evidence case is the imported Oracle HR model mapped to a target model
derived from it, with every target column accounted for. Each negative control
removes one thing and asserts the document says so. Expected counts are
computed from the models, never written down.
"""

from __future__ import annotations

import csv
import io
import json
import logging

import pytest

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services import mapping as m
from app.services.ddl_import.importer import import_ddl
from tests.test_ddl_round_trip import DDL

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)


def _hr() -> SynthesizedModel:
    model = import_ddl((DDL / "oracle" / "hr.sql").read_bytes(), "oracle", "hr.sql").model
    assert model is not None
    # stable ids as a save gives them, so renames can be told from removals
    for entity in model.entities:
        for number, column in enumerate(entity.columns, start=1):
            column.stable_id = number
    return model


def _target() -> SynthesizedModel:
    """A dimensional model derived from HR: what a mapping document maps into."""
    def col(name: str, dtype: str, **kw: object) -> ColumnSchema:
        return ColumnSchema(name=name, data_type=dtype, **kw)  # type: ignore[arg-type]

    dim = EntitySchema(entity_name="dim_employee", entity_type="DIMENSION", columns=[  # type: ignore[arg-type]
        col("employee_key", "INTEGER", is_primary_key=True, stable_id=1),
        col("employee_id", "NUMERIC(6,0)", stable_id=2),
        col("full_name", "VARCHAR(46)", stable_id=3),
        col("email", "VARCHAR(25)", stable_id=4),
        col("hire_date", "DATE", stable_id=5),
        col("department_name", "VARCHAR(30)", stable_id=6),
        col("salary", "NUMERIC(8,2)", stable_id=7),
        col("load_batch", "VARCHAR(20)", stable_id=8),
    ])
    return SynthesizedModel(paradigm="KIMBALL", entities=[dim], relationships=[])  # type: ignore[arg-type]


def _entries(source: SynthesizedModel, target: SynthesizedModel) -> list[m.Entry]:
    ref = m.ref_for
    t = "dim_employee"
    return [
        m.Entry("M-0001", "derived", ref(target, t, "employee_key"),
                fields={"rule_description": "surrogate key assigned by the load"}),
        m.Entry("M-0002", "mapped", ref(target, t, "employee_id"), [ref(source, "EMPLOYEES", "EMPLOYEE_ID")],
                {"transformation_type": "IDENTITY"}),
        m.Entry("M-0003", "mapped", ref(target, t, "full_name"),
                [ref(source, "EMPLOYEES", "FIRST_NAME"), ref(source, "EMPLOYEES", "LAST_NAME")],
                {"transformation_type": "TRANSFORMATION", "logic": "FIRST_NAME || ' ' || LAST_NAME"}),
        m.Entry("M-0004", "mapped", ref(target, t, "email"), [ref(source, "EMPLOYEES", "EMAIL")],
                {"transformation_type": "IDENTITY"}),
        m.Entry("M-0005", "mapped", ref(target, t, "hire_date"), [ref(source, "EMPLOYEES", "HIRE_DATE")]),
        m.Entry("M-0006", "mapped", ref(target, t, "department_name"),
                [ref(source, "DEPARTMENTS", "DEPARTMENT_NAME")],
                {"transformation_type": "JOIN", "join_filter": "EMPLOYEES.DEPARTMENT_ID = DEPARTMENTS.DEPARTMENT_ID"}),
        m.Entry("M-0007", "mapped", ref(target, t, "salary"), [ref(source, "EMPLOYEES", "SALARY")]),
        m.Entry("M-0008", "constant", ref(target, t, "load_batch"), fields={"rule_description": "the batch id"}),
    ]


def _counted(rep: m.Report) -> int:
    return rep.mapped + rep.unmapped + rep.pending + rep.silent + rep.in_drift


def test_hr_to_a_derived_target_accounts_for_every_target_column() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    rep = m.report(entries, [], source, target)
    total = sum(len(e.columns) for e in target.entities)
    unmapped = sum(1 for e in entries if e.kind in m.UNMAPPED_KINDS)
    assert (rep.total, rep.mapped, rep.unmapped, rep.silent, rep.pending) == (
        total, len(entries) - unmapped, unmapped, 0, 0)
    assert _counted(rep) == rep.total and rep.complete
    assert rep.summary().startswith(f"{len(entries) - unmapped} of {total} target columns mapped, "
                                    f"{unmapped} explicitly unmapped, 0 silent")


def test_control_a_pending_proposal_is_never_counted_as_mapped() -> None:
    source, target = _hr(), _target()
    kept = [e for e in _entries(source, target) if e.target.column not in ("email", "hire_date")]
    before = m.report(kept, [], source, target)
    proposals = m.propose(source, target, kept)
    assert {p.target.column for p in proposals} >= {"email", "hire_date"}
    after = m.report(kept, proposals, source, target)
    assert after.mapped == before.mapped  # the proposals moved nothing into "mapped"
    assert after.pending == before.silent - after.silent > 0 and not after.complete
    assert {r.target["column"] for r in after.rows if r.status == "pending"} >= {"email", "hire_date"}


def test_control_deleting_one_accepted_mapping_is_reported_as_missing() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    removed = entries.pop(3)  # email
    rep = m.report(entries, [], source, target)
    assert rep.silent == 1 and not rep.complete
    assert [r.target["column"] for r in rep.rows if r.status == "silent"] == [removed.target.column]
    exported = m.export_rows(m.DocumentInfo("hr", "HR", "Dim"), rep, source)
    assert [row["Status"] for row in exported if row["Target column"] == "email"] == ["SILENT: no entry (error)"]


def test_control_removing_a_mapped_source_column_raises_the_drift_flag() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    employees = next(e for e in source.entities if e.entity_name == "EMPLOYEES")
    employees.columns = [c for c in employees.columns if c.name != "EMAIL"]
    rep = m.report(entries, [], source, target)
    row = next(r for r in rep.rows if r.target["column"] == "email")
    assert row.status == "drift" and row.drift == ["source column missing: EMPLOYEES.EMAIL"]
    assert row.entry is not None  # flagged, never dropped
    assert rep.in_drift == 1 and rep.mapped == len([e for e in entries if e.kind == "mapped"]) - 1
    assert not rep.complete


def test_a_renamed_source_column_is_flagged_with_its_new_name() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    email = next(c for e in source.entities for c in e.columns if c.name == "EMAIL")
    email.name = "EMAIL_ADDRESS"
    row = next(r for r in m.report(entries, [], source, target).rows
               if r.target["column"] == "email")
    assert row.drift == ["source column missing: EMPLOYEES.EMAIL (renamed to EMAIL_ADDRESS?)"]


def test_an_entry_whose_target_column_is_gone_is_kept_and_flagged() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    target.entities[0].columns = [c for c in target.entities[0].columns if c.name != "salary"]
    rep = m.report(entries, [], source, target)
    orphan = [r for r in rep.rows if r.entry is not None and r.entry.target.column == "salary"]
    assert len(orphan) == 1 and orphan[0].drift == ["target column missing: dim_employee.salary"]
    assert rep.orphaned == 1 and not rep.complete


def test_a_deleted_source_model_puts_every_mapped_entry_in_drift() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)
    rep = m.report(entries, [], None, target, source_deleted=True)
    assert rep.mapped == 0 and rep.in_drift == sum(1 for e in entries if e.kind == "mapped")
    assert rep.unmapped == sum(1 for e in entries if e.kind in m.UNMAPPED_KINDS)  # they need no source


def test_proposals_carry_both_scores_and_the_confidence_they_make() -> None:
    source, target = _hr(), _target()
    proposals = m.propose(source, target, [])
    email = [p for p in proposals if p.target.column == "email"]
    assert email and email[0].sources[0] == m.ref_for(source, "EMPLOYEES", "EMAIL")
    for p in proposals:
        assert 0 <= p.name_similarity <= 1 and 0 <= p.type_compatibility <= 1
        assert p.confidence == round(m.NAME_WEIGHT * p.name_similarity + m.TYPE_WEIGHT * p.type_compatibility, 4)
        assert p.confidence >= m.PROPOSAL_FLOOR and p.status == "pending"
    # Control: a column with an entry, or already offered, is not proposed again.
    decided = _entries(source, target)[3:4]
    assert not [p for p in m.propose(source, target, decided) if p.target.column == "email"]
    assert not [p for p in m.propose(source, target, [], email) if p.target.column == "email"]


def test_type_compatibility_distinguishes_families() -> None:
    assert m.type_compatibility("NUMBER(6,0)", "INTEGER") == 1.0
    assert m.type_compatibility("DATE", "VARCHAR(10)") == 0.5
    assert m.type_compatibility("VARCHAR2(20)", "DATE") == 0.0


@pytest.mark.parametrize(("kind", "sources", "fields", "reason"), [
    ("mapped", [], {}, "at least one source"),
    ("constant", [m.ColumnRef("A", "b")], {}, "has no source column"),
    ("copied", [], {}, "kind must be"),
    ("mapped", [m.ColumnRef("A", "b")], {"transformation_type": "COPY"}, "transformation_type"),
    ("mapped", [m.ColumnRef("A", "b")], {"scd_type": 7}, "scd_type"),
    ("mapped", [m.ColumnRef("A", "b")], {"approved_by": "x"}, "unknown fields"),
    ("mapped", [m.ColumnRef("A", "b"), m.ColumnRef("A", "c")], {}, "many-to-one"),
])
def test_an_entry_the_rules_refuse_says_why(kind: str, sources: list[m.ColumnRef], fields: dict[str, object],
                                             reason: str) -> None:
    with pytest.raises(m.MappingError, match=reason):
        m.validate_entry(kind, sources, fields)


def test_every_export_carries_the_completeness_line_and_every_target_column() -> None:
    source, target = _hr(), _target()
    entries = _entries(source, target)[:-1]  # load_batch left silent
    rep = m.report(entries, m.propose(source, target, entries), source, target)
    doc = m.DocumentInfo("HR to dim", "HR", "Dim")
    rows = m.export_rows(doc, rep, source)
    assert len(rows) == rep.total
    for fmt, export in m.EXPORTERS.items():
        text = export(doc, rep, rows)
        assert rep.summary() in (json.loads(text)["completeness"]["summary"] if fmt == "json" else text), fmt
    lines = [line for line in m.to_csv(doc, rep, rows).splitlines() if not line.startswith("#")]
    table = list(csv.reader(io.StringIO("\n".join(lines))))
    assert tuple(table[0]) == m.EXPORT_COLUMNS and len(table) - 1 == rep.total
    full_name = next(r for r in rows if r["Target column"] == "full_name")
    assert full_name["Source column"] == "FIRST_NAME; LAST_NAME"
    assert full_name["Transformation type"] == "DIRECT TRANSFORMATION"


def test_the_digest_changes_with_the_content() -> None:
    source, target = _hr(), _target()
    entry = _entries(source, target)[1]
    before = m.digest(entry)
    entry.fields = {**entry.fields, "rule_description": "copied"}
    assert m.digest(entry) != before
