"""Omission is not fabrication — the end-to-end half of "omit rather than guess".

The synthesis system prompt already instructs it: *"an omission costs nothing,
but a guess is exported into a data contract as fact, which is worse than saying
nothing."* Two tests already cover adjacent paths —
`test_unbounded_pattern_is_not_guessed_at` covers one linter path, and
`test_a_response_omitting_every_new_field_still_validates` covers IR-level
omission. Neither proves the property the product actually claims.

**The claim is about the export, not the model.** The harm named in the prompt
is a guess *exported into a data contract as fact*, so the property is: when an
IR field is unset, no emitter invents a value for it. That is fully testable
offline — no provider is involved, because the question is what the deterministic
pipeline does with a sparse input, not what an LLM chooses to emit.

## The fixture design is the whole test

A sparse fixture only discriminates if a plausible fabrication would be
**visible**. If the thin input still admits an obvious output, a fabricating
implementation and an honest one produce identical artifacts and the test proves
nothing — standard 8, arriving inside a test written to prove honesty under
uncertainty.

So every column here *invites* a specific, nameable fabrication:

| Column | The guess it invites |
| :-- | :-- |
| `email` | a regex pattern, or an email format rule |
| `status` | an enumerated CHECK / `accepted_values` |
| `created_at` | `DEFAULT CURRENT_TIMESTAMP` |
| `age` | a 0–120 range rule |
| `phone` | a phone-format regex |
| `country_code` | a length or enum constraint |

Each is a constraint a competent engineer might add without being asked, and
each is absent from the declared model. The test asserts the absence by name.

## The discriminating half

Asserting "no constraints appear" passes trivially on an emitter that emits no
constraints at all. So the same six columns are also exercised **with** their
constraints declared, and each must then appear. Two fixtures differing only in
whether the optional fields are set — correction C7's lesson, applied
deliberately this time rather than discovered.
"""

from __future__ import annotations

import json

import pytest
import sqlglot
import yaml
from sqlglot import exp

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    Paradigm,
    SynthesizedModel,
)
from app.services.exporter_service import ExporterService
from app.services.synthesis_engine import _SYSTEM_PROMPT

DATASET = "omission_ds"

# The optional physical constraints a synthesised model may carry. Enumerated
# from the IR rather than hand-listed, so a new one added to `ColumnSchema`
# fails `test_every_invented_constraint_field_is_covered` until it is either
# exercised here or explicitly excused.
OPTIONAL_CONSTRAINTS = (
    "is_unique",
    "default_value",
    "check_expression",
    "regex_pattern",
    "min_value",
    "max_value",
)

# Columns chosen because each invites a specific, nameable guess.
BAIT = ("email", "status", "created_at", "age", "phone", "country_code")

TYPES = {
    "email": "VARCHAR(255)",
    "status": "VARCHAR(32)",
    "created_at": "TIMESTAMP",
    "age": "INTEGER",
    "phone": "VARCHAR(32)",
    "country_code": "VARCHAR(8)",
}


def _model(*, declared: bool) -> SynthesizedModel:
    """The same entity twice, differing only in whether constraints are set.

    `declared=False` is the sparse case the product promises is safe.
    `declared=True` is the discriminating counterpart: without it, every
    absence assertion below would pass on an exporter that emits nothing.
    """
    columns = [
        ColumnSchema(
            name="account_id",
            data_type="INTEGER",
            is_primary_key=True,
            is_nullable=False,
            ordinal_position=0,
        )
    ]
    for position, name in enumerate(BAIT, start=1):
        extra: dict = {}
        if declared:
            extra = {
                "email": {"regex_pattern": "^[^@]+@[^@]+$"},
                "status": {"check_expression": "status IN ('ACTIVE','CLOSED')"},
                "created_at": {"default_value": "CURRENT_TIMESTAMP"},
                "age": {"min_value": 0.0, "max_value": 120.0},
                "phone": {"regex_pattern": "^[0-9+ -]{7,20}$"},
                "country_code": {"is_unique": True},
            }[name]
        columns.append(
            ColumnSchema(
                name=name,
                data_type=TYPES[name],
                ordinal_position=position,
                **extra,
            )
        )
    return SynthesizedModel(
        paradigm=Paradigm.KIMBALL,
        entities=[EntitySchema(entity_name="dim_account", columns=columns)],
        relationships=[],
    )


SPARSE = _model(declared=False)
DECLARED = _model(declared=True)


def _ddl(model: SynthesizedModel) -> str:
    return ExporterService().generate_ddl(model, "postgres")


def _odcs(model: SynthesizedModel) -> dict:
    return yaml.safe_load(
        ExporterService().export_data_contract(model, "odcs", DATASET)["datacontract.yaml"]
    )


def _dbt_schema(model: SynthesizedModel) -> dict:
    files = ExporterService().generate_dbt_project(model)
    for path, content in files.items():
        if path.endswith((".yml", ".yaml")) and "models" in path:
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict) and parsed.get("models"):
                return parsed
    return {}


# ---------------------------------------------------------------------------
# Fixture sanity — the bait must actually be bare
# ---------------------------------------------------------------------------
def test_the_sparse_model_declares_no_optional_constraint() -> None:
    """Without this the whole file could pass on a fixture that quietly set them."""
    for column in SPARSE.entities[0].columns:
        if column.is_primary_key:
            continue
        set_fields = [
            field
            for field in OPTIONAL_CONSTRAINTS
            if getattr(column, field) not in (None, False)
        ]
        assert not set_fields, f"{column.name} declares {set_fields}; it must be bare"


def test_every_invented_constraint_field_is_covered() -> None:
    """Breadth from the IR (standard 11).

    A new optional constraint added to `ColumnSchema` is a new thing an emitter
    could invent. It fails here until someone exercises it or excuses it.
    """
    ir_optional = {
        name
        for name, f in ColumnSchema.model_fields.items()
        if f.default in (None, False)
    }
    # Excused, with reasons: these are not physical constraints an emitter could
    # fabricate into a contract as fact.
    excused = {
        "stable_id",  # server-assigned wire identity, never model-supplied
        "ordinal_position",  # ordering, set by the pipeline
        "is_primary_key",  # structural, and PK nullability is a product rule
        "is_foreign_key",
        "references",  # structural; covered by the cross-artifact gate
        "description",  # free text; absence is visible, not fabricated
        "is_pii",
        "pii_type",  # classification; PII_EXPOSURE lints its absence
        "is_metric",
        "aggregation",  # semantic-layer concerns, not contract constraints
        "is_nullable",  # has a safe default and is compared across artifacts
    }
    uncovered = sorted(ir_optional - set(OPTIONAL_CONSTRAINTS) - excused)
    assert not uncovered, (
        f"optional IR fields an emitter could invent, neither exercised nor "
        f"excused: {uncovered}"
    )


# ---------------------------------------------------------------------------
# The property: nothing is invented
# ---------------------------------------------------------------------------
def test_ddl_invents_no_constraint_for_a_bare_column() -> None:
    """Parsed, not grepped — a CHECK inside a column definition is structure."""
    invented: dict[str, list[str]] = {}
    for statement in sqlglot.parse(_ddl(SPARSE), read="postgres"):
        if not isinstance(statement, exp.Create):
            continue
        for entry in statement.this.expressions:
            if not isinstance(entry, exp.ColumnDef) or entry.name not in BAIT:
                continue
            found = [
                type(c.kind).__name__
                for c in entry.constraints
                if isinstance(
                    c.kind,
                    (
                        exp.CheckColumnConstraint,
                        exp.DefaultColumnConstraint,
                        exp.UniqueColumnConstraint,
                    ),
                )
            ]
            if found:
                invented[entry.name] = found
    assert not invented, f"DDL invented constraints nobody declared: {invented}"


def test_odcs_invents_no_quality_rule_for_a_bare_column() -> None:
    """A fabricated quality rule is the worst case: it ships as a contract term."""
    invented = {}
    for entity in _odcs(SPARSE)["schema"]:
        for prop in entity.get("properties", []):
            if prop["name"] not in BAIT:
                continue
            quality = prop.get("quality") or []
            options = prop.get("logicalTypeOptions") or {}
            # maxLength derives from VARCHAR(n) in the declared type, so it is
            # a restatement rather than an invention. Anything else is not.
            invented_options = {k: v for k, v in options.items() if k != "maxLength"}
            if quality or invented_options:
                invented[prop["name"]] = {"quality": quality, "options": invented_options}
    assert not invented, f"ODCS invented rules nobody declared: {invented}"


def test_dbt_invents_no_test_for_a_bare_column() -> None:
    """`accepted_values` on an undeclared `status` is the classic fabrication.

    **Found by this test, live.** A column called `status` with no declared
    constraint acquires three permitted values it never had, and they ship in
    the dbt project as a contract the customer's data is then tested against.
    A user whose statuses are PENDING and DONE gets a red build on their own
    correct data — which is H11's failure, arrived at from the other direction.

    Recorded as a strict xfail rather than fixed in this commit: the fix belongs
    with the emitter and its own dbt gates, and every defect here becomes a
    failing test before it becomes a fix.
    """
    schema = _dbt_schema(SPARSE)
    invented = {}
    for model in schema.get("models", []):
        for column in model.get("columns", []):
            if column["name"] not in BAIT:
                continue
            tests = column.get("data_tests") or column.get("tests") or []
            if tests:
                invented[column["name"]] = tests
    assert not invented, f"dbt invented tests nobody declared: {invented}"


def test_the_sparse_model_still_exports_completely() -> None:
    """Sparse, not broken — the reason iteration works.

    Under-specification must cost coverage, not correctness. If a bare model
    failed to export, "omit rather than guess" would be advice that breaks the
    product when followed.
    """
    ddl = _ddl(SPARSE)
    for name in BAIT:
        assert name in ddl, f"{name} vanished from the DDL of a sparse model"
    assert _odcs(SPARSE)["schema"], "a sparse model produced an empty contract"
    assert _dbt_schema(SPARSE).get("models"), "a sparse model produced no dbt models"


# ---------------------------------------------------------------------------
# The discriminating half — declared constraints must appear
# ---------------------------------------------------------------------------
def test_a_declared_default_reaches_the_ddl() -> None:
    """Otherwise every absence test above passes on an emitter that emits nothing.

    Correction C7's lesson applied on purpose: this and the absence assertions
    differ only in whether the fixture sets the field, which is the only
    arrangement under which the absence means anything.

    Only `default_value` is asserted here. `check_expression` and `is_unique`
    reach ODCS and dbt rather than postgres DDL — that is register criterion
    C2's stated shape, not a defect, and asserting them here would be this
    file's own author guessing at where a constraint ought to land.
    """
    line = next(
        ln for ln in _ddl(DECLARED).splitlines() if ln.strip().startswith("created_at")
    )
    assert "DEFAULT" in line.upper(), f"declared default missing: {line!r}"


def test_declared_constraints_do_reach_the_contract() -> None:
    """The discriminating half for the quality rules.

    Two landing sites, because ODCS uses two: an enumerated or pattern rule
    becomes a `quality` entry, a numeric range becomes `logicalTypeOptions`.
    Asserting only one would leave the other's absence untested.
    """
    props = {
        prop["name"]: prop
        for entity in _odcs(DECLARED)["schema"]
        for prop in entity.get("properties", [])
    }
    assert props["email"].get("quality"), "declared regex did not reach ODCS quality"
    assert props["status"].get("quality"), "declared check did not reach ODCS quality"
    age_options = props["age"].get("logicalTypeOptions") or {}
    assert age_options.get("minimum") == 0.0 and age_options.get("maximum") == 120.0, (
        f"declared range did not reach ODCS: {age_options}"
    )
    assert props["country_code"].get("unique") is True, "declared uniqueness lost"


# ---------------------------------------------------------------------------
# The instruction itself
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field", OPTIONAL_CONSTRAINTS)
def test_the_system_prompt_names_every_constraint_it_asks_to_be_omitted(
    field: str,
) -> None:
    """The instruction must cover what the IR can carry.

    A constraint the IR accepts but the prompt never mentions is one the model
    decides about silently — which is exactly the guess this property forbids,
    arriving through the gap between the schema and the instruction.
    """
    assert field in _SYSTEM_PROMPT, (
        f"'{field}' is an optional constraint the IR carries, but the synthesis "
        f"prompt gives no omit-rather-than-guess instruction for it"
    )


def test_the_prompt_states_the_reason_not_just_the_rule() -> None:
    """The 'why' is load-bearing and has been edited away before.

    A bare rule invites a well-meaning rewrite that softens it. The reason — a
    guess becomes contractual fact — is what makes the rule survive review.
    """
    prompt = _SYSTEM_PROMPT.lower()
    assert "omission costs nothing" in prompt
    assert "guess" in prompt and "contract" in prompt


def test_json_round_trip_preserves_absence() -> None:
    """Absence must survive serialisation as absence, not become a default.

    If the wire format turned an unset constraint into an explicit value, every
    assertion above would still pass while the contract shipped the invention.
    """
    payload = json.loads(SPARSE.model_dump_json())
    for column in payload["entities"][0]["columns"]:
        if column["name"] not in BAIT:
            continue
        for field in OPTIONAL_CONSTRAINTS:
            assert column.get(field) in (None, False), (
                f"{column['name']}.{field} materialised as {column.get(field)!r}"
            )
