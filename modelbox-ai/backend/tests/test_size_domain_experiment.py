"""The experiment harness runs end to end before it is allowed to cost anything.

**This is the test that should have existed for D10.** Two of the three
instrument defects in that run — a missing system prompt, and a harness calling
the gateway instead of the product — would have been caught by exercising the
runner against a stub before paying for twelve calls. Both were found afterwards,
from the numbers, which is the expensive way.

So: the whole path, with a scripted gateway and no provider. It asserts the
things that cost money to discover — that the report is written, that the layer
split works, that a failed draw is recorded rather than dropped, and above all
that the `pipeline` condition actually goes through the product.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel


def _model(entities: int = 2, *, cyclic: bool = False) -> SynthesizedModel:
    built = [
        EntitySchema(
            entity_name=f"dim_{i}",
            entity_type="DIMENSION",  # type: ignore[arg-type]
            description="d",
            columns=[
                ColumnSchema(name=f"k_{i}", data_type="INTEGER", is_primary_key=True),
                ColumnSchema(name=f"v_{i}", data_type="VARCHAR(32)", description="v"),
            ],
        )
        for i in range(entities)
    ]
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=built,
        relationships=[],
    )


class _Gateway:
    """Returns a canned model and records what it was asked."""

    def __init__(self, model: SynthesizedModel | None = None, fail_on: int | None = None):
        self.model = model or _model()
        self.fail_on = fail_on
        self.calls = 0
        self.system_prompts: list[str | None] = []
        self.providers = {"anthropic_cloud": {"default_model": "stub-model-1"}}

    async def structured_completion(self, **kwargs: Any) -> SynthesizedModel:
        self.calls += 1
        self.system_prompts.append(kwargs.get("system_prompt"))
        if self.fail_on is not None and self.calls == self.fail_on:
            raise RuntimeError("provider exploded")
        return self.model.model_copy(deep=True)

    def _egress_class(self, _provider: str) -> str:
        return "cloud"


@pytest.fixture()
def opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELBOX_ALLOW_PROVIDER_CALLS", "1")
    monkeypatch.setenv("MODELBOX_RUN_CONFORMANCE", "1")


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path, gateway: _Gateway, *argv: str) -> dict:
    import asyncio

    from app.services import llm_gateway as gateway_module
    from scripts import run_size_domain_experiment as runner

    monkeypatch.setattr(gateway_module, "LLMGateway", lambda _settings: gateway)
    out = tmp_path / "experiment.json"
    code = asyncio.run(
        runner.main(
            ["--provider", "anthropic_cloud", "--out", str(out), "--repeats", "1", *argv]
        )
    )
    assert code == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_it_refuses_without_both_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The precondition, asserted rather than assumed.

    Every other test here sets the gates, so without this one the suite would
    pass just as happily if the guard were deleted.
    """
    from scripts import run_size_domain_experiment as runner

    monkeypatch.delenv("MODELBOX_ALLOW_PROVIDER_CALLS", raising=False)
    monkeypatch.setenv("MODELBOX_RUN_CONFORMANCE", "1")
    with pytest.raises(SystemExit) as excinfo:
        runner._refuse_unless_opted_in()
    assert excinfo.value.code == 2


@pytest.mark.usefixtures("opted_in")
def test_the_pipeline_condition_goes_through_the_product(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The whole reason this experiment exists.

    `bare` and `pipeline` must not be the same code path with different labels.
    A canned model with no repairable issues makes exactly one call under each,
    so call count cannot distinguish them — the distinguishing fact is that
    `pipeline` reaches `SynthesisEngine.build_graph`, and that is what is
    asserted, at the boundary the D10 harness failed to cross.
    """
    from app.services.synthesis_engine import SynthesisEngine

    seen: list[str] = []
    original = SynthesisEngine.build_graph

    async def _spy(self, request, **kwargs):  # type: ignore[no-untyped-def]
        seen.append("build_graph")
        return await original(self, request, **kwargs)

    monkeypatch.setattr(SynthesisEngine, "build_graph", _spy)
    gateway = _Gateway()
    report = _run(
        monkeypatch, tmp_path, gateway, "--cells", "ecommerce-orders", "--conditions", "bare,pipeline"
    )

    assert seen == ["build_graph"], "the pipeline condition did not run the product"
    assert gateway.calls == 2
    assert set(report["cells"]) == {"ecommerce-orders/bare", "ecommerce-orders/pipeline"}


@pytest.mark.usefixtures("opted_in")
def test_both_conditions_send_the_product_system_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The D10 defect, guarded on both paths this time.

    `test_conformance_sends_the_prompt` asserts the argument appears in one
    call site's source. That guard did not survive the harness growing a second
    path, so this one reads what the gateway was actually handed.
    """
    from app.services.synthesis_engine import _SYSTEM_PROMPT

    gateway = _Gateway()
    _run(monkeypatch, tmp_path, gateway, "--cells", "ecommerce-orders")
    assert gateway.system_prompts == [_SYSTEM_PROMPT, _SYSTEM_PROMPT]


@pytest.mark.usefixtures("opted_in")
def test_findings_are_normalised_and_split_by_layer(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Per entity, and separated — the two properties the analysis depends on.

    A raw count is not comparable across cells that differ in size on purpose,
    and pooling the layers would discard the signal the two competing
    predictions actually disagree about.
    """
    gateway = _Gateway(_model(entities=4))
    report = _run(
        monkeypatch, tmp_path, gateway, "--cells", "ecommerce-orders", "--conditions", "bare"
    )
    draw = report["draws"][0]

    assert draw["entity_count"] == 4
    assert draw["findings"] == draw["structural_findings"] + draw["tabular_findings"]
    assert draw["findings_per_entity"] == pytest.approx(draw["findings"] / 4)
    # Four unrelated dimensions with no edges: the orphan rule is structural,
    # so this fixture proves the split can be non-zero rather than merely
    # arithmetically consistent.
    assert draw["structural_findings"] > 0, "fixture cannot exercise the layer split"


@pytest.mark.usefixtures("opted_in")
def test_a_failed_draw_is_recorded_not_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A mean over three draws and one over five are different measurements.

    Silently dropping a failure would shrink the denominator and leave the
    report claiming a spread it never observed.
    """
    gateway = _Gateway(fail_on=1)
    report = _run(
        monkeypatch,
        tmp_path,
        gateway,
        "--cells",
        "ecommerce-orders",
        "--conditions",
        "bare",
    )
    cell = report["cells"]["ecommerce-orders/bare"]
    assert cell["draws_attempted"] == 1
    assert cell["draws_scored"] == 0
    assert "provider exploded" in report["draws"][0]["error"]


@pytest.mark.usefixtures("opted_in")
def test_every_cell_runs_and_is_summarised(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The full 2x2, so a missing cell fails here rather than after 40 calls."""
    from scripts.experiment_prompts import CELLS

    gateway = _Gateway()
    report = _run(monkeypatch, tmp_path, gateway)
    assert gateway.calls == len(CELLS) * 2
    for cell_id in CELLS:
        for condition in ("bare", "pipeline"):
            assert report["cells"][f"{cell_id}/{condition}"]["draws_scored"] == 1


@pytest.mark.usefixtures("opted_in")
def test_an_unknown_cell_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import asyncio

    from app.services import llm_gateway as gateway_module
    from scripts import run_size_domain_experiment as runner

    monkeypatch.setattr(gateway_module, "LLMGateway", lambda _settings: _Gateway())
    code = asyncio.run(
        runner.main(
            [
                "--provider",
                "anthropic_cloud",
                "--out",
                str(tmp_path / "x.json"),
                "--cells",
                "not-a-cell",
            ]
        )
    )
    assert code == 1
