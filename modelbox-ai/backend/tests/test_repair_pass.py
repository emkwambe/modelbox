"""The linter's findings reach the model that produced them (Task 7).

`GraphEngine.validate` has always run on the synthesised graph. Its report went
to the canvas for a human to fix by hand and, in the engine, into
``logger.warning`` as a *count* — the issues themselves were discarded. So the
product owned a deterministic thirteen-rule checker and never told the model
what it found.

That is the one shape of self-correction with evidence behind it. A model asked
to critique its own output gets worse; a model handed an **external**
deterministic verdict does not. The linter is external in exactly that sense.

**These tests are about the gate, not the prompt.** A repair pass with no
acceptance test is a second chance to make the model worse, and there is no
reason to assume a provider's second answer beats its first. Every test below
either proves the gate accepts a real improvement or proves it refuses
everything else — including a "repair" that trades a cycle for two new defects.

**No test here contacts a provider.** The stub gateway returns a scripted second
answer, which is what lets the acceptance rule be tested at all: a live model
would make the interesting cases unreproducible.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)
from app.services.graph_engine import GraphEngine
from app.services.synthesis_engine import _REPAIRABLE_CODES, SynthesisEngine


class _ScriptedGateway:
    """Returns the queued models in order, and counts how often it was called."""

    def __init__(self, *models: SynthesizedModel) -> None:
        self._models = list(models)
        self.calls = 0
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    async def structured_completion(
        self,
        task: str,
        prompt: str,
        response_model: type[Any],
        system_prompt: str | None = None,
        **_: Any,
    ) -> SynthesizedModel:
        self.calls += 1
        self.prompts.append(prompt)
        self.system_prompts.append(system_prompt or "")
        return self._models[min(self.calls - 1, len(self._models) - 1)]


class _FailingGateway(_ScriptedGateway):
    async def structured_completion(self, *a: Any, **k: Any) -> SynthesizedModel:
        self.calls += 1
        if self.calls == 1:
            return self._models[0]
        raise RuntimeError("provider exploded during repair")


def _column(name: str, **over: Any) -> ColumnSchema:
    base: dict[str, Any] = {
        "name": name,
        "data_type": "VARCHAR(50)",
        "is_primary_key": False,
        "is_foreign_key": False,
        "is_pii": False,
    }
    base.update(over)
    return ColumnSchema(**base)


def _entity(name: str, columns: list[ColumnSchema], **over: Any) -> EntitySchema:
    return EntitySchema(
        entity_name=name,
        entity_type=over.pop("entity_type", "TABLE"),
        columns=columns,
        **over,
    )


def _clean() -> SynthesizedModel:
    """A graph with no repairable issues."""
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity(
                "customer",
                [
                    _column("customer_id", is_primary_key=True, data_type="BIGINT"),
                    _column("name"),
                ],
            )
        ],
        relationships=[],
    )


def _dangling() -> SynthesizedModel:
    """A foreign key pointing at an entity that is not in the model."""
    return SynthesizedModel(
        paradigm="3NF",  # type: ignore[arg-type]
        entities=[
            _entity(
                "orders",
                [
                    _column("order_id", is_primary_key=True, data_type="BIGINT"),
                    _column(
                        "customer_id",
                        data_type="BIGINT",
                        is_foreign_key=True,
                        references="customer.customer_id",
                    ),
                ],
            )
        ],
        relationships=[
            RelationshipSchema(
                from_ref="orders.customer_id",
                to_ref="customer.customer_id",
                cardinality="N:1",  # type: ignore[arg-type]
            )
        ],
    )


def _dangling_repaired() -> SynthesizedModel:
    """The same model with the missing entity supplied."""
    model = _dangling()
    model.entities.append(
        _entity(
            "customer",
            [
                _column("customer_id", is_primary_key=True, data_type="BIGINT"),
                _column("name"),
            ],
        )
    )
    return model


def _engine(gateway: Any) -> SynthesisEngine:
    return SynthesisEngine(session=None, gateway=gateway)  # type: ignore[arg-type]


def _issues(model: SynthesizedModel) -> list[str]:
    report = GraphEngine().validate(model.entities, model.relationships)
    return [i.code for i in report.issues if i.code in _REPAIRABLE_CODES]


# ---------------------------------------------------------------------------
# Preconditions — the fixtures must actually exhibit what they claim
# ---------------------------------------------------------------------------
def test_the_broken_fixture_is_broken_and_the_clean_one_is_clean() -> None:
    """Without this, every assertion below could be passing vacuously.

    A `_dangling()` that the linter did not flag would make the repair pass a
    no-op and three tests would go green having exercised nothing.
    """
    assert "DANGLING_REF" in _issues(_dangling())
    assert _issues(_clean()) == []
    assert _issues(_dangling_repaired()) == []


def test_every_repairable_code_is_one_the_linter_can_emit() -> None:
    """A typo in the allowlist would silently narrow the pass to nothing.

    `_REPAIRABLE_CODES` is matched against `issue.code` by string, so
    `"DANGLNG_REF"` would never match and never fail — the repair pass would
    simply stop firing for that class with no signal anywhere.
    """
    import inspect

    source = inspect.getsource(GraphEngine)
    for code in _REPAIRABLE_CODES:
        assert f'code="{code}"' in source, f"{code} is not emitted by GraphEngine"


def test_the_advisory_codes_are_deliberately_excluded() -> None:
    """The S5-2 guard, as an assertion rather than a comment.

    `MISSING_SLA` fires when an entity claims a tier and states no SLA. Feeding
    it back reads as "supply an SLA" — inventing a governance commitment that is
    exported into a data contract as fact, which is the exact defect the system
    prompt was rewritten to suppress. If someone widens the allowlist to "all
    codes", this is what stops it.
    """
    for code in (
        "MISSING_SLA",
        "NAMING_CONVENTION",
        "MISSING_DESCRIPTION",
        "MISSING_GRAIN",
        "FAN_OUT_RISK",
        "PII_EXPOSURE",
        "ORPHAN_ENTITY",
    ):
        assert code not in _REPAIRABLE_CODES


# ---------------------------------------------------------------------------
# The pass itself
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_clean_graph_costs_no_second_call() -> None:
    """No repairable issue, no repair — and therefore no extra egress.

    Every repair is a real provider request written to the ledger before it is
    sent. A pass that fired unconditionally would double the egress of every
    synthesis in the product to fix nothing.
    """
    gateway = _ScriptedGateway(_clean())
    model, report = await _engine(gateway)._repair_once(
        _clean(), GraphEngine().validate(_clean().entities, _clean().relationships),
        _request(), user_id=None,
    )
    assert gateway.calls == 0
    assert _issues(model) == []
    assert report.is_valid


@pytest.mark.asyncio
async def test_a_repair_that_fixes_the_defect_is_kept() -> None:
    broken = _dangling()
    gateway = _ScriptedGateway(_dangling_repaired())
    model, report = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert gateway.calls == 1
    assert _issues(model) == []
    assert {e.entity_name for e in model.entities} == {"orders", "customer"}
    assert not [i for i in report.issues if i.code == "DANGLING_REF"]


@pytest.mark.asyncio
async def test_a_repair_that_does_not_improve_is_discarded() -> None:
    """The gate, in the case it exists for.

    The provider returns the *same broken graph*. Without an acceptance rule
    this would be adopted silently, and the pass would have spent a provider
    call to replace a model with itself — or, with a worse second answer, to
    make the product's output worse than the model it charged for.
    """
    broken = _dangling()
    gateway = _ScriptedGateway(_dangling())
    model, report = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert gateway.calls == 1
    assert model is broken, "the original model must be returned unchanged"
    assert "DANGLING_REF" in [i.code for i in report.issues]


@pytest.mark.asyncio
async def test_a_repair_that_trades_one_defect_for_two_is_discarded() -> None:
    """Strictly fewer, not merely different.

    A rule of "the defect I named is gone" would accept this: the dangling
    reference is resolved, and two entities with no primary key arrive in its
    place. Counting repairable issues rather than checking the named one is what
    makes the trade visible.
    """
    broken = _dangling()
    worse = _dangling_repaired()
    for entity in worse.entities:
        for column in entity.columns:
            column.is_primary_key = False

    gateway = _ScriptedGateway(worse)
    model, _ = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert len(_issues(worse)) >= len(_issues(broken)), "fixture must be a real trade"
    assert model is broken


@pytest.mark.asyncio
async def test_a_provider_failure_during_repair_keeps_the_original() -> None:
    """A failed repair is not a failed synthesis.

    The user still gets the model they asked for, with the issues shown on the
    canvas exactly as they were before this pass existed. Synthesis is the
    expensive call; losing it because an optional second call failed would make
    the product worse for adding a feature.
    """
    broken = _dangling()
    gateway = _FailingGateway(broken)
    gateway.calls = 1  # the synthesis call already happened
    model, report = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert model is broken
    assert "DANGLING_REF" in [i.code for i in report.issues]


@pytest.mark.asyncio
async def test_the_repair_prompt_lists_only_repairable_codes() -> None:
    """What is sent is what the allowlist permits, not the whole report.

    Asserted on the prompt actually handed to the gateway rather than on the
    allowlist, because the allowlist is only a claim about behaviour until
    something reads the string that leaves.
    """
    broken = _dangling()
    broken.entities[0].tier = "TIER_1_CRITICAL"  # type: ignore[assignment]
    report = GraphEngine().validate(broken.entities, broken.relationships)
    assert any(i.code == "MISSING_SLA" for i in report.issues), "fixture precondition"

    gateway = _ScriptedGateway(_dangling_repaired())
    await _engine(gateway)._repair_once(broken, report, _request(), user_id=None)

    sent = gateway.prompts[0]
    assert "DANGLING_REF" in sent
    assert "MISSING_SLA" not in sent
    assert "do not supply a tier" in gateway.system_prompts[0].lower()


@pytest.mark.asyncio
async def test_a_repair_that_deletes_the_offending_column_is_discarded() -> None:
    """Deleting the table is not repairing it.

    Every repairable code is satisfiable by removing whatever carries it, and a
    gate that counts findings cannot see the difference: drop the foreign key
    and the `DANGLING_REF` goes with it, one repairable issue becomes zero, and
    the count gate accepts a model that answered the question by discarding it.

    This is not a claim that providers do this deliberately. It is that the gate
    could not have told us if one did — and the same hole sits in the
    conformance instrument, where a raw finding count rewards a model that
    emits fewer tables (`GraphScore.lint_delta_per_entity`).
    """
    broken = _dangling()
    gutted = _dangling()
    gutted.entities[0].columns = [
        c for c in gutted.entities[0].columns if c.name != "customer_id"
    ]
    gutted.relationships = []

    # Precondition: without the surface check this trade *passes* the count
    # gate. A test whose fixture cannot exercise the defect proves nothing.
    assert len(_issues(gutted)) < len(_issues(broken)), (
        "fixture must actually reduce the repairable count, or the gate under "
        "test is never reached"
    )

    gateway = _ScriptedGateway(gutted)
    model, _ = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert model is broken, "a repair that deletes a column must be discarded"


@pytest.mark.asyncio
async def test_a_repair_that_deletes_the_offending_entity_is_discarded() -> None:
    """The same hole one level up, and the more expensive one.

    Losing a column costs a field; losing an entity costs a table the user
    described and will not be told is gone.
    """
    broken = _dangling_repaired()
    for column in broken.entities[1].columns:
        column.is_primary_key = False  # customer now carries MISSING_PK

    gutted = _dangling_repaired()
    gutted.entities = [e for e in gutted.entities if e.entity_name != "customer"]
    gutted.entities[0].columns = [
        c for c in gutted.entities[0].columns if c.name != "customer_id"
    ]
    gutted.relationships = []

    assert len(_issues(gutted)) < len(_issues(broken)), "fixture must be a real trade"

    gateway = _ScriptedGateway(gutted)
    model, _ = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert model is broken, "a repair that deletes an entity must be discarded"


@pytest.mark.asyncio
async def test_a_repair_that_only_adds_is_still_accepted() -> None:
    """The check refuses losses, not changes.

    Stated as its own test because a subset check written as equality would
    reject every genuine repair — `MISSING_PK` is fixed by *adding* a key
    column, and `DANGLING_REF` by adding the missing table. If this goes red the
    gate has stopped accepting repairs at all, which the count alone would not
    reveal.
    """
    broken = _dangling()
    gateway = _ScriptedGateway(_dangling_repaired())
    model, _ = await _engine(gateway)._repair_once(
        broken,
        GraphEngine().validate(broken.entities, broken.relationships),
        _request(),
        user_id=None,
    )
    assert model is not broken, "an additive repair must still be accepted"
    assert {e.entity_name for e in model.entities} == {"orders", "customer"}


@pytest.mark.asyncio
async def test_telemetry_records_an_accepted_repair_that_strips_descriptions() -> None:
    """The measurement that the size x domain run needed and did not have.

    One AML draw came back with 17 findings against a typical 3, and 79 of 158
    columns carrying no description. Nothing recorded whether the repair pass
    had done that or the draw was simply a bad sample, and because bare and
    pipeline are independent samples the comparison could not settle it.

    **The trade this asserts is one the gate permits by construction.** The
    acceptance test counts `_REPAIRABLE_CODES` only, and `MISSING_DESCRIPTION`
    is deliberately not one of them — feeding it back invites the model to
    invent prose. So a repair may remove a dangling reference, strip every
    description in the model, and pass: repairable count fell, and the gate has
    no opinion about anything else. The surface check refuses *lost* columns; it
    says nothing about what a surviving column still carries.

    This test does not argue the gate is wrong. It makes the trade visible in
    the record, so the next run can say whether it actually happens.
    """
    # The pre-repair model has to *carry* descriptions, or "stripped" has
    # nothing to measure and the assertion below reads 0 < 0. The first draft
    # of this fixture missed that and the test failed for the wrong reason.
    broken = _dangling()
    for entity in broken.entities:
        for column in entity.columns:
            column.description = f"what {column.name} holds"

    repaired = _dangling_repaired()
    for entity in repaired.entities:
        for column in entity.columns:
            column.description = None

    # Two models, in order: `build_graph` calls the gateway once to synthesise
    # and once to repair. Queueing only the repaired one would make the first
    # call return it, leaving nothing broken and the repair never firing —
    # which is what the first draft of this test did.
    engine = _engine(_ScriptedGateway(broken, repaired))
    telemetry: dict[str, Any] = {}
    model, _ = await engine.build_graph(_request(), telemetry=telemetry)

    assert telemetry["repair_fired"] is True
    assert telemetry["repair_accepted"] is True, (
        "fixture must exercise an accepted repair, or the telemetry under test "
        "is never populated"
    )
    assert model is not broken
    # The trade itself: fewer repairable issues, fewer descriptions.
    assert telemetry["repairable_after"] < telemetry["repairable_before"]
    assert telemetry["described_columns_after"] < telemetry["described_columns_before"]
    # And no column was lost, which is why the surface check did not fire.
    assert telemetry["columns_after"] >= telemetry["columns_before"]


@pytest.mark.asyncio
async def test_telemetry_records_a_rejected_repair() -> None:
    """`repair_accepted` must distinguish the two outcomes.

    A flag that is always true would have made the run above look explained
    while explaining nothing.
    """
    worse = _dangling_repaired()
    for entity in worse.entities:
        for column in entity.columns:
            column.is_primary_key = False

    engine = _engine(_ScriptedGateway(_dangling(), worse))
    telemetry: dict[str, Any] = {}
    model, _ = await engine.build_graph(_request(), telemetry=telemetry)

    assert telemetry["repair_fired"] is True
    assert telemetry["repair_accepted"] is False
    assert telemetry["findings_after"] == telemetry["findings_before"]
    assert model.entities[0].entity_name == "orders"


@pytest.mark.asyncio
async def test_telemetry_records_a_repair_that_never_fired() -> None:
    """A clean model must read as "did not fire", not as "rejected"."""
    engine = _engine(_ScriptedGateway(_clean()))
    telemetry: dict[str, Any] = {}
    await engine.build_graph(_request(), telemetry=telemetry)

    assert telemetry["repair_fired"] is False
    assert telemetry["repair_accepted"] is False
    assert telemetry["repairable_before"] == 0


def _request() -> Any:
    from app.schemas.data_model import SynthesizeRequest

    return SynthesizeRequest(
        source_type="natural_language",  # type: ignore[arg-type]
        content="orders and customers",
        target_paradigm="3NF",  # type: ignore[arg-type]
        dialect="postgres",
    )
