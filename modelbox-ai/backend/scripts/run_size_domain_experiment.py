"""Size x domain, through the product pipeline (the H1 + §11.4 experiment).

Two questions in one run, because they are separable at no extra cost:

1. **Does the product's own pipeline change the numbers?** Every D10 figure so
   far came from `structured_completion` called directly — step one of four.
   Cardinality normalisation and the repair pass, both shipped and both aimed at
   the axes that failed, have never been evaluated on provider output. Here each
   cell is generated twice, `--conditions bare,pipeline`, from the same prompt.
2. **Is the AML failure size or specialisation?** Four cells crossing those
   factors; see `experiment_prompts` for the registered prediction.

## Reference-free, deliberately

Nothing here scores against a gold graph. Two of the four cells have no gold
graph and writing one would mean inventing a reference answer for a domain in
order to grade a model against it — and the D10 experience is that a
single-reference metric mostly measures whether the model picked the same words.

The instrument is the product's own thirteen-rule linter, which needs no
reference, and the measure is **findings per entity**, not raw findings. A raw
count is not comparable across sizes — the whole point here is that sizes differ
— and it rewards omission, since a model emitting fewer tables emits fewer
findings. Entity count is reported beside every number so that stays checkable.

Findings are split by **layer**: a code attached to the graph's shape
(`CYCLIC_FK`, `ORPHAN_ENTITY`, `FAN_OUT_RISK`, `DANGLING_REF`) versus one
attached to a table or column. The two literatures being separated predict
damage in different layers, so pooling them would discard the discriminating
signal.

## Repeats

`--repeats` defaults to 5. Providers are sampled, one draw per cell tells you
nothing about a difference between cells, and the run is cheap enough that a
spread is affordable. Every draw is kept: the report carries per-draw numbers as
well as the cell mean, because a mean over five draws with a wide spread and one
with a narrow spread are different findings and a single number hides that.

## Cost

`cells x conditions x repeats` provider calls, plus up to one extra per
`pipeline` draw when the linter finds something repairable. The default is
4 x 2 x 5 = **40 calls, up to 60 with repairs**. Nothing here runs without both
fail-closed gates set explicitly.

    MODELBOX_ALLOW_PROVIDER_CALLS=1 MODELBOX_RUN_CONFORMANCE=1 \\
        .venv/Scripts/python -m scripts.run_size_domain_experiment \\
        --provider anthropic_cloud --out ../docs/marketing/size-domain-experiment.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

#: Codes describing the graph's shape rather than one table's contents. The
#: split is the experiment's discriminating variable, so it is declared here
#: rather than inferred from a code's name at read time.
_STRUCTURAL_CODES: frozenset[str] = frozenset(
    {"CYCLIC_FK", "DANGLING_REF", "ORPHAN_ENTITY", "FAN_OUT_RISK"}
)


def _refuse_unless_opted_in() -> None:
    """Both gates, explicitly, exactly as the conformance runner requires.

    This script makes real provider calls and costs real money. It is not the
    D10 gate and must never be mistaken for it — but it reaches a provider, so
    it opts in the same way, and an operator who has disabled egress must not be
    able to trip it by running the wrong file.
    """
    missing = [
        name
        for name in ("MODELBOX_ALLOW_PROVIDER_CALLS", "MODELBOX_RUN_CONFORMANCE")
        if os.environ.get(name) != "1"
    ]
    if missing:
        print(
            "refusing to run: this script calls a provider and "
            f"{', '.join(missing)} is not set to 1.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _layered(codes: list[str]) -> tuple[int, int]:
    """`(structural, tabular)` finding counts."""
    structural = sum(1 for c in codes if c in _STRUCTURAL_CODES)
    return structural, len(codes) - structural


async def main(argv: list[str] | None = None) -> int:
    _refuse_unless_opted_in()

    from app.core.config import Settings
    from app.schemas.data_model import SynthesizedModel, SynthesizeRequest
    from app.services.graph_engine import GraphEngine
    from app.services.llm_gateway import LLMGateway
    from app.services.synthesis_engine import _SYSTEM_PROMPT, SynthesisEngine
    from scripts.experiment_prompts import CELLS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--conditions",
        default="bare,pipeline",
        help="'bare' calls the gateway directly; 'pipeline' runs the product.",
    )
    parser.add_argument("--cells", default=",".join(CELLS))
    args = parser.parse_args(argv)

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    cells = [c.strip() for c in args.cells.split(",") if c.strip()]
    unknown = set(cells) - set(CELLS)
    if unknown:
        print(f"refusing to run: unknown cells {sorted(unknown)}", file=sys.stderr)
        return 1

    settings = Settings()  # type: ignore[call-arg]
    gateway = LLMGateway(settings)
    graph = GraphEngine()
    # `None` for the session, deliberately. `build_graph` never persists, so it
    # needs none — and passing a live one would let an experiment write to the
    # metadata store. If a future edit moves a database call into that path this
    # fails loudly on the first draw rather than quietly writing rows.
    engine = SynthesisEngine(session=None, gateway=gateway, graph_engine=graph)  # type: ignore[arg-type]

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    model_identifier = gateway.providers[args.provider]["default_model"]
    draws: list[dict[str, object]] = []

    clock = time.monotonic()

    def elapsed() -> float:
        return time.monotonic() - clock

    total = len(cells) * len(conditions) * args.repeats
    print(
        f"{total} draws: {len(cells)} cells x {len(conditions)} conditions x "
        f"{args.repeats} repeats. Up to {total + len(cells) * args.repeats} "
        f"provider calls once repairs are counted.",
        flush=True,
    )

    for cell_id in cells:
        paradigm, description, size, domain, target = CELLS[cell_id]
        print(f"\n=== {cell_id} ({size}, {domain}) ===", flush=True)
        request = SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content=description,
            target_paradigm=paradigm,  # type: ignore[arg-type]
            dialect="postgres",
            llm_override=args.provider,
        )
        for condition in conditions:
            for draw in range(args.repeats):
                telemetry: dict[str, object] = {}
                try:
                    if condition == "pipeline":
                        candidate, report = await engine.build_graph(
                            request, telemetry=telemetry
                        )
                        codes = [i.code for i in report.issues]
                    else:
                        candidate = await gateway.structured_completion(
                            task="unstructured_doc_parsing",
                            prompt=engine._build_prompt(request),
                            response_model=SynthesizedModel,
                            system_prompt=_SYSTEM_PROMPT,
                            llm_override=args.provider,
                        )
                        codes = [
                            i.code
                            for i in graph.validate(
                                candidate.entities, candidate.relationships
                            ).issues
                        ]
                except Exception as exc:  # noqa: BLE001
                    # A failed draw is recorded, never silently dropped: a cell
                    # whose mean is over three draws instead of five is a
                    # different measurement, and the report has to say so.
                    draws.append(
                        {
                            "cell": cell_id,
                            "size": size,
                            "domain": domain,
                            "condition": condition,
                            "draw": draw,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(f"  [{elapsed():>5.0f}s] {cell_id}/{condition}/{draw}: FAILED {exc}", flush=True)
                    continue

                entities = len(candidate.entities)
                structural, tabular = _layered(codes)
                draws.append(
                    {
                        "cell": cell_id,
                        "size": size,
                        "domain": domain,
                        "target_entity_count": target,
                        "condition": condition,
                        "draw": draw,
                        "entity_count": entities,
                        "relationship_count": len(candidate.relationships),
                        "findings": len(codes),
                        "findings_per_entity": (len(codes) / entities) if entities else None,
                        "structural_findings": structural,
                        "structural_per_entity": (structural / entities) if entities else None,
                        "tabular_findings": tabular,
                        "codes": sorted(set(codes)),
                        # Empty on the `bare` condition, which runs no repair.
                        # Its absence there is the honest record, not a gap.
                        "repair": telemetry,
                        "candidate": candidate.model_dump(mode="json"),
                    }
                )
                # `flush` on every progress line, not as a nicety.
                #
                # Python block-buffers stdout when it is a pipe, and the launcher
                # pipes through Select-String to drop LiteLLM's banner. So the
                # only thing reaching the terminal during a 40-call run was the
                # logger's stderr, which is unbuffered — pages of
                # `agg_time_column` warnings and not one result line. A run that
                # costs money and takes minutes has to show progress, and
                # "looks hung" is indistinguishable from "is hung" precisely
                # when you most want to know which.
                note = ""
                if telemetry.get("repair_accepted"):
                    note = (
                        f"  REPAIR ACCEPTED {telemetry['findings_before']}"
                        f"->{telemetry['findings_after']} findings, "
                        f"{telemetry['described_columns_before']}"
                        f"->{telemetry['described_columns_after']} described cols"
                    )
                elif telemetry.get("repair_fired"):
                    note = "  repair rejected"
                print(
                    f"  [{elapsed():>5.0f}s] {cell_id}/{condition}/{draw}: "
                    f"{entities} entities, {len(codes)} findings "
                    f"({structural} structural){note}",
                    flush=True,
                )

    def _summary(rows: list[dict]) -> dict[str, object]:
        ok = [r for r in rows if "error" not in r]
        per_entity = [r["findings_per_entity"] for r in ok if r["findings_per_entity"] is not None]
        structural = [
            r["structural_per_entity"] for r in ok if r["structural_per_entity"] is not None
        ]
        return {
            "draws_attempted": len(rows),
            "draws_scored": len(ok),
            "mean_findings_per_entity": statistics.fmean(per_entity) if per_entity else None,
            # Reported beside the mean, never instead of it. Five draws with a
            # wide spread and five with a narrow one are different findings.
            "stdev_findings_per_entity": (
                statistics.stdev(per_entity) if len(per_entity) > 1 else None
            ),
            "mean_structural_per_entity": statistics.fmean(structural) if structural else None,
            "mean_entity_count": (
                statistics.fmean([r["entity_count"] for r in ok]) if ok else None
            ),
            # The repair pass's own record. `repairs_accepted` counts draws the
            # gate let through; `repairs_that_cost_findings` counts the ones it
            # let through that ended with *more* total findings than they
            # started with — which the gate permits by construction, since it
            # weighs repairable codes only.
            "repairs_fired": sum(1 for r in ok if r.get("repair", {}).get("repair_fired")),
            "repairs_accepted": sum(
                1 for r in ok if r.get("repair", {}).get("repair_accepted")
            ),
            "repairs_that_cost_findings": sum(
                1
                for r in ok
                if r.get("repair", {}).get("repair_accepted")
                and r["repair"]["findings_after"] > r["repair"]["findings_before"]
            ),
            "repairs_that_cost_descriptions": sum(
                1
                for r in ok
                if r.get("repair", {}).get("repair_accepted")
                and r["repair"]["described_columns_after"]
                < r["repair"]["described_columns_before"]
            ),
        }

    report = {
        "run_started_at": started,
        "provider": args.provider,
        "model_identifier": model_identifier,
        "repeats": args.repeats,
        "conditions": conditions,
        "instrument": (
            "The product's thirteen-rule linter, reference-free. Findings per "
            "entity, split into structural codes "
            f"({sorted(_STRUCTURAL_CODES)}) and tabular codes. No gold graph is "
            "involved and no F1 is computed."
        ),
        "cells": {
            f"{cell}/{condition}": _summary(
                [r for r in draws if r["cell"] == cell and r["condition"] == condition]
            )
            for cell in cells
            for condition in conditions
        },
        "draws": draws,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    for key, value in report["cells"].items():  # type: ignore[union-attr]
        mean = value["mean_findings_per_entity"]  # type: ignore[index]
        print(
            f"  {key:34} {'n/a' if mean is None else f'{mean:.3f}'} findings/entity "
            f"({value['draws_scored']}/{value['draws_attempted']} draws)"  # type: ignore[index]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
