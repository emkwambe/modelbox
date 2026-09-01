"""Task 4 — the cross-artifact consistency gate (register standard 10).

Every gate before this one asks whether *one* artifact satisfies its own
consumer. That question cannot see a disagreement **between** artifacts, and the
disagreement is the defect a user actually experiences — H11 shipped a valid dbt
contract and a valid seed that contradicted each other, and only `dbt build`
could see it.

**This closes the category rather than checking pairs.** A *projection* reads
one IR field out of one emitted artifact:

    (artifact, ir_field) -> {(entity, column): normalised value}

The gate groups projections **by IR field** and asserts they all agree. No pair
is named anywhere, so a third artifact deriving from the same field is covered
the day its projection is registered. A list of two comparisons behind a
pleasant interface would be pair-checking wearing this one's clothes.

Breadth is closed from **both** ends, which is standard 11 built in rather than
asserted afterwards:

* from the IR — every field of ``ColumnSchema`` must carry >=2 projections or
  appear in ``EXEMPT`` with a written reason, so a new field forces a decision;
* from the artifacts — every contract format and DDL dialect the exporter
  accepts must appear in the registry, so a fifth format cannot arrive
  uncovered.

And a field with exactly **one** projection is a failure, not a pass: it asserts
nothing while looking registered. That is the standards 8/11/12/14 shape
appearing inside the gate built to close a different category, so it is checked
explicitly.

Projections parse — sqlglot for DDL, yaml for ODCS, json for Avro. Never
substrings. The whole programme exists because 76 defects hid behind string
assertions.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlglot
import yaml
from sqlglot import exp

from app.schemas.data_model import ColumnSchema, SynthesizedModel
from app.services.exporter_service import ExporterService

GOLD = Path(__file__).resolve().parent / "fixtures" / "gold"
DATASET = "consistency_ds"

# Dialects whose DDL sqlglot can read back. `generate_ddl` accepts more than
# this; `test_every_ddl_dialect_is_projected_or_exempt` holds the difference to
# an explicit list rather than letting it go unnoticed.
DDL_DIALECTS = ("postgres", "snowflake", "bigquery", "duckdb")


# ---------------------------------------------------------------------------
# Models — gold, plus mutated copies that make the fields differ
# ---------------------------------------------------------------------------
def _load_gold() -> dict[str, SynthesizedModel]:
    models = {}
    for path in sorted(GOLD.glob("*.json")):
        if path.name == "index.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        models[path.stem] = SynthesizedModel.model_validate(
            {
                "paradigm": raw["paradigm"],
                "entities": raw["entities"],
                "relationships": raw["relationships"],
            }
        )
    return models


GOLD_MODELS = _load_gold()


def _discriminating(model: SynthesizedModel) -> SynthesizedModel:
    """A copy where ``is_nullable`` and ``is_primary_key`` are not the same fact.

    **Mandatory, not defensive, and re-checked on 2026-09-01 when the gold set
    became six.** On all six gold graphs every primary key is
    non-nullable and every non-key column is nullable, so `not is_nullable` and
    `is_primary_key` are the *same partition* — correction C7, which already
    cost one sprint a meaningless assertion. A projection that read the wrong
    field would agree with every other projection on the gold graphs alone.

    This makes the first non-key column NOT NULL, so the two fields disagree on
    at least one column of every model. Standard 14: the fixtures the product
    ships cannot discriminate, so the discriminating case is synthesised.
    """
    mutated = copy.deepcopy(model)
    for entity in mutated.entities:
        for column in entity.columns:
            if not column.is_primary_key:
                column.is_nullable = False
                break
    return mutated


MODELS: dict[str, SynthesizedModel] = {
    **GOLD_MODELS,
    **{f"{name}+notnull": _discriminating(m) for name, m in GOLD_MODELS.items()},
}


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------
Reading = dict[tuple[str, str], object]


@dataclass(frozen=True)
class Projection:
    artifact: str
    field: str
    read: Callable[[SynthesizedModel], Reading]


def _exporter() -> ExporterService:
    return ExporterService()


def _canon(name: str) -> str:
    """Canonical entity name for joining readings across artifacts.

    Artifacts name the same entity by their own conventions — `dim_customer` in
    DDL and ODCS, `DimCustomer` as an Avro record. Those are not a
    disagreement, they are house style per format, so the join canonicalises
    rather than requiring equality. `test_entity_names_canonicalise_injectively`
    keeps the canonicalisation from merging two distinct entities, which would
    silently compare one entity's column against another's.
    """
    return name.replace("_", "").lower()


def _resolve(model: SynthesizedModel, raw_entity: str) -> str:
    """Map an artifact's entity name back to the IR's, for readable failures."""
    target = _canon(raw_entity)
    for entity in model.entities:
        if _canon(entity.entity_name) == target:
            return entity.entity_name
    return raw_entity


def _ddl_reading(model: SynthesizedModel, dialect: str) -> tuple[Reading, Reading]:
    """(`is_nullable`, `is_primary_key`) read out of parsed DDL."""
    ddl = _exporter().generate_ddl(model, dialect)
    nullable: Reading = {}
    primary: Reading = {}
    for statement in sqlglot.parse(ddl, read=dialect):
        if not isinstance(statement, exp.Create):
            continue
        schema = statement.this
        if not isinstance(schema, exp.Schema):
            continue
        table = _resolve(model, schema.this.name)
        table_pks: set[str] = set()
        for entry in schema.expressions:
            if isinstance(entry, exp.PrimaryKey):
                table_pks |= {c.name or c.this.name for c in entry.expressions}
        for entry in schema.expressions:
            if not isinstance(entry, exp.ColumnDef):
                continue
            kinds = [c.kind for c in entry.constraints]
            not_null = any(isinstance(k, exp.NotNullColumnConstraint) for k in kinds)
            inline_pk = any(
                isinstance(k, exp.PrimaryKeyColumnConstraint) for k in kinds
            )
            key = (table, entry.name)
            nullable[key] = not not_null
            primary[key] = inline_pk or entry.name in table_pks
    return nullable, primary


def _ddl_nullable(dialect: str) -> Callable[[SynthesizedModel], Reading]:
    return lambda model: _ddl_reading(model, dialect)[0]


def _ddl_primary(dialect: str) -> Callable[[SynthesizedModel], Reading]:
    return lambda model: _ddl_reading(model, dialect)[1]


def _odcs_reading(model: SynthesizedModel) -> tuple[Reading, Reading]:
    contract = yaml.safe_load(
        _exporter().export_data_contract(model, "odcs", DATASET)["datacontract.yaml"]
    )
    nullable: Reading = {}
    primary: Reading = {}
    for entity in contract["schema"]:
        for prop in entity.get("properties", []):
            key = (_resolve(model, entity["name"]), prop["name"])
            # ODCS states the *positive* obligation; the IR states the
            # permission. Inverted here rather than compared loosely, because
            # "required" and "nullable" agreeing by accident is exactly the
            # kind of coincidence this gate exists to rule out.
            nullable[key] = not prop["required"]
            primary[key] = bool(prop["primaryKey"])
    return nullable, primary


def _avro_nullable(model: SynthesizedModel) -> Reading:
    """Avro encodes nullability as a union with ``null``, not as a flag."""
    reading: Reading = {}
    files = _exporter().export_data_contract(model, "avro", DATASET)
    for content in files.values():
        schema = json.loads(content)
        for field in schema["fields"]:
            ftype = field["type"]
            reading[(_resolve(model, schema["name"]), field["name"])] = (
                isinstance(ftype, list) and "null" in ftype
            )
    return reading


PROJECTIONS: list[Projection] = [
    *[
        Projection(f"ddl:{d}", "is_nullable", _ddl_nullable(d))
        for d in DDL_DIALECTS
    ],
    *[
        Projection(f"ddl:{d}", "is_primary_key", _ddl_primary(d))
        for d in DDL_DIALECTS
    ],
    Projection("odcs", "is_nullable", lambda m: _odcs_reading(m)[0]),
    Projection("odcs", "is_primary_key", lambda m: _odcs_reading(m)[1]),
    Projection("avro", "is_nullable", _avro_nullable),
]

# Fields deliberately not compared, each with the reason. **Exemption by
# omission is not allowed** — that is how a field stops being checked without
# anyone deciding it should.
EXEMPT: dict[str, str] = {
    "name": "the join key of every projection; it cannot disagree with itself",
    "data_type": (
        "each artifact renders its own type system, and equality across them is "
        "not the property. A comparison would have to be loosened until it "
        "passed, which proves nothing. Per-artifact type fidelity is asserted "
        "against each consumer's own parser in test_artifact_fidelity.py."
    ),
    "stable_id": "wire identity, carried only by Protobuf tags (B6/PL-006)",
    "ordinal_position": "ordering, not a per-column value; DDL and Avro carry it implicitly",
    "description": "free text, emitted as comments/doc by some artifacts and dropped by others",
    "is_foreign_key": "only DDL emits referential constraints; single-consumer",
    "references": "only DDL emits referential constraints; single-consumer",
    "is_pii": "ODCS classification only; no second consumer emits it structurally",
    "pii_type": "ODCS classification only; no second consumer emits it structurally",
    "is_metric": "semantic-layer only (Cube/MetricFlow); not a contract concept",
    "aggregation": "semantic-layer only (Cube/MetricFlow); not a contract concept",
    "min_value": "quality rule; ODCS quality block and dbt tests, compared by the dbt gates",
    "max_value": "quality rule; ODCS quality block and dbt tests, compared by the dbt gates",
    "regex_pattern": "quality rule; ODCS quality block and dbt tests, compared by the dbt gates",
    "is_unique": "DDL UNIQUE and dbt unique test; compared by the dbt gates, not here",
    "default_value": "DDL only; no contract format carries a default expression",
    "check_expression": "DDL CHECK and the seed generator; compared by dbt build (H11)",
}

# Nullability is genuinely absent from Protobuf output, and that is a finding
# rather than a projection. Recorded here so it cannot be mistaken for an
# oversight; see test_protobuf_carries_no_field_presence.
PROTOBUF_NULLABILITY_FINDING = (
    "proto3 emits no `optional` keyword, so every scalar field has implicit "
    "presence and the artifact carries no nullability information at all"
)


def _fields_with_projections() -> dict[str, list[Projection]]:
    grouped: dict[str, list[Projection]] = {}
    for projection in PROJECTIONS:
        grouped.setdefault(projection.field, []).append(projection)
    return grouped


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_name", sorted(MODELS))
@pytest.mark.parametrize("field", sorted(_fields_with_projections()))
def test_artifacts_derived_from_the_same_ir_field_agree(
    field: str, model_name: str
) -> None:
    """The category, not a pair.

    Every artifact that projects ``field`` must produce the same mapping. The
    failure message names the artifacts and the exact columns, because "two
    artifacts disagree" is not actionable and "ODCS says dim_customer.email is
    required and Avro says it is nullable" is.
    """
    model = MODELS[model_name]
    readings = {p.artifact: p.read(model) for p in _fields_with_projections()[field]}

    shared = set.intersection(*(set(r) for r in readings.values()))
    assert shared, f"no columns are common to {sorted(readings)}; nothing compared"

    disagreements: dict[tuple[str, str], dict[str, object]] = {}
    for key in sorted(shared):
        values = {artifact: reading[key] for artifact, reading in readings.items()}
        if len(set(values.values())) > 1:
            disagreements[key] = values

    assert not disagreements, (
        f"artifacts disagree about '{field}' on {model_name}:\n"
        + "\n".join(f"  {e}.{c}: {v}" for (e, c), v in disagreements.items())
    )


@pytest.mark.parametrize("field", sorted(_fields_with_projections()))
def test_each_field_actually_varies_across_the_fixtures(field: str) -> None:
    """A projection over a constant proves nothing (standard 8).

    If every column in every model had the same value for a field, all
    projections would agree trivially — including one that read the wrong field
    entirely. This is what the mutated copies are for, and this test is what
    proves they did their job.
    """
    observed: set[object] = set()
    projection = _fields_with_projections()[field][0]
    for model in MODELS.values():
        observed |= set(projection.read(model).values())
    assert len(observed) > 1, (
        f"'{field}' takes the single value {observed} across every fixture, so "
        f"the agreement test above cannot fail"
    )


def test_nullability_and_primary_key_are_not_the_same_partition() -> None:
    """Correction C7, asserted rather than assumed.

    On the gold graphs alone, `not is_nullable` and `is_primary_key` describe
    the same set of columns — so a projection that read one while claiming the
    other would agree with everything. The mutated copies exist to break that,
    and this test fails if they ever stop.
    """
    offenders = []
    for name, model in MODELS.items():
        pairs = {
            (not c.is_nullable, c.is_primary_key)
            for e in model.entities
            for c in e.columns
        }
        if all(a == b for a, b in pairs):
            offenders.append(name)
    assert len(offenders) < len(MODELS), (
        "no fixture distinguishes non-nullability from primary-keyness, so a "
        "projection reading the wrong field would pass (C7)"
    )


# ---------------------------------------------------------------------------
# Breadth, closed from both ends
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model_name", sorted(MODELS))
def test_entity_names_canonicalise_injectively(model_name: str) -> None:
    """The join key must not merge two entities.

    `_canon` strips underscores and case so `DimCustomer` joins to
    `dim_customer`. If two distinct entities ever canonicalised the same, the
    gate would compare one entity's column against another's and report
    agreement or disagreement about something that does not exist.
    """
    names = [e.entity_name for e in MODELS[model_name].entities]
    canonical = [_canon(n) for n in names]
    assert len(set(canonical)) == len(names), (
        f"entity names collide under canonicalisation in {model_name}: {names}"
    )


def test_every_ir_field_is_projected_or_exempt() -> None:
    """From the IR side: a new field forces a decision.

    Enumerated from ``ColumnSchema.model_fields`` rather than a hand list, so
    adding a field to the IR fails here until someone says whether artifacts
    must agree about it.
    """
    projected = set(_fields_with_projections())
    undecided = sorted(set(ColumnSchema.model_fields) - projected - set(EXEMPT))
    assert not undecided, (
        f"IR fields with neither a projection nor a written exemption: "
        f"{undecided}. Add projections, or exempt them with a reason."
    )


def test_no_exemption_is_silent() -> None:
    """An exemption without a reason is an omission with better manners."""
    empty = sorted(f for f, reason in EXEMPT.items() if not reason.strip())
    assert not empty, f"exemptions with no stated reason: {empty}"
    stale = sorted(set(EXEMPT) - set(ColumnSchema.model_fields))
    assert not stale, f"exemptions for fields the IR no longer has: {stale}"


def test_no_field_has_a_single_projection() -> None:
    """The sharpest of the breadth checks.

    One projection asserts nothing while appearing registered — the same shape
    as standards 8, 11, 12 and 14, occurring inside the gate written to close a
    different category. A field either has something to compare against or it is
    exempt.
    """
    lonely = {
        field: [p.artifact for p in projections]
        for field, projections in _fields_with_projections().items()
        if len(projections) < 2
    }
    assert not lonely, f"fields with only one projection, comparing nothing: {lonely}"


def test_every_contract_format_is_projected_or_exempt() -> None:
    """From the artifact side: a fifth contract format cannot arrive uncovered.

    The formats are discovered by asking the exporter what it accepts, not from
    a list here — otherwise this test is itself an enumeration and drifts the
    moment a format is added.
    """
    exporter = _exporter()
    accepted = []
    for candidate in ("odcs", "avro", "protobuf", "json_schema", "openapi", "thrift"):
        try:
            exporter.export_data_contract(
                next(iter(GOLD_MODELS.values())), candidate, DATASET
            )
        except Exception:  # noqa: BLE001,S112 - anything but success means unsupported
            continue
        accepted.append(candidate)

    assert accepted, "fixture sanity: the exporter accepts no contract format"
    projected = {p.artifact for p in PROJECTIONS}
    uncovered = [
        fmt
        for fmt in accepted
        if fmt not in projected and fmt != "protobuf"
    ]
    assert not uncovered, (
        f"contract formats the exporter emits but nothing projects: {uncovered}"
    )


def test_every_ddl_dialect_is_projected_or_explicitly_left_out() -> None:
    """Same closure on the DDL side."""
    projected = {
        p.artifact.split(":", 1)[1] for p in PROJECTIONS if p.artifact.startswith("ddl:")
    }
    assert projected == set(DDL_DIALECTS), (
        f"DDL_DIALECTS and the registered projections disagree: "
        f"{projected} vs {set(DDL_DIALECTS)}"
    )


def test_protobuf_carries_no_field_presence() -> None:
    """The recorded finding, asserted so it cannot be quietly forgotten.

    Protobuf is the one contract format with no ``is_nullable`` projection, and
    the reason is a property of the emitted artifact rather than a decision
    about the gate: proto3 emits no ``optional`` keyword, so every scalar field
    has implicit presence and nullability is simply absent.

    This test fails the day the emitter starts emitting ``optional`` — which is
    the day a projection should be added and this exemption removed.
    """
    model = _discriminating(next(iter(GOLD_MODELS.values())))
    proto = "\n".join(
        _exporter().export_data_contract(model, "protobuf", DATASET).values()
    )
    assert "optional " not in proto, (
        "protobuf now emits field presence, so it can and should be projected "
        f"for is_nullable; remove this test. Reason it was exempt: "
        f"{PROTOBUF_NULLABILITY_FINDING}"
    )
