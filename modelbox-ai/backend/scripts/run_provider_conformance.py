"""Provider conformance harness (D10) — the sprint's only real provider calls.

**Run instruction**

    # 1. local runtime up, with the router's default_model pulled
    docker compose -f docker/docker-compose.appliance.yml --profile airgap up -d ollama-engine
    docker exec modelbox-ollama-engine ollama pull qwen2.5-coder:32b

    # 2. at least one cloud key, so there is something to compare against
    export ANTHROPIC_API_KEY=...

    # 3. both opt-ins, deliberately, and never in CI
    cd backend
    MODELBOX_ALLOW_PROVIDER_CALLS=1 MODELBOX_RUN_CONFORMANCE=1 \
        .venv/Scripts/python -m scripts.run_provider_conformance \
        --providers local_ollama,anthropic_cloud \
        --out ../docs/marketing/conformance-report.json

**Two opt-ins, not one, and that is the point.**
``MODELBOX_ALLOW_PROVIDER_CALLS`` is the appliance-wide fail-closed gate built in
Task 1 — the choke point refuses without it, and an import scan proves nothing
outside the gateway can reach a provider at all. ``MODELBOX_RUN_CONFORMANCE`` is
this script's own. Either alone refuses. The programme has held a hard
zero-provider-calls constraint since the audit; breaking it here is deliberate,
and one flag away from an accident is not far enough.

This module makes no provider call at import. Everything network-facing lives
below ``main()``, which is only reached under ``__main__`` — so importing it,
collecting it, or reading it can never produce egress. Asserted by
``tests/test_conformance_isolation.py``.

Every threshold is **imported** from ``conformance_threshold``, never restated
here. A harness that carried its own copy of a number could drift from the one
committed before the first call, which would quietly undo the guarantee that
ordering bought.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
GOLD = BACKEND / "tests" / "fixtures" / "gold"

RUN_FLAG = "MODELBOX_RUN_CONFORMANCE"
EGRESS_FLAG = "MODELBOX_ALLOW_PROVIDER_CALLS"

# Prompts live in `conformance_prompts`, with the calibration rule they were
# written to and a per-graph well-posedness judgement recorded before the run.
# Not in the gold fixtures: those are extracted from templates.ts behind a drift
# guard, and are a curriculum asset that must not be edited to suit a harness.


def _refuse_unless_opted_in() -> None:
    """Both flags, or nothing happens. Checked before anything is constructed."""
    missing = [flag for flag in (RUN_FLAG, EGRESS_FLAG) if os.environ.get(flag) != "1"]
    if missing:
        raise SystemExit(
            f"refusing to run: {', '.join(missing)} not set to 1. This script "
            f"makes real provider calls and is the only thing in the programme "
            f"permitted to. Set both deliberately; never in CI."
        )


def _gold_graphs() -> list[tuple[str, object, str]]:
    """(id, model, prompt) for each gold graph.

    The prompt supplies the paradigm explicitly. Withholding it would score the
    model's guess at a naming convention rather than its schema design —
    `hub_`/`lnk_`/`sat_` is Data Vault convention, not a fact about banking, and
    `SynthesizeRequest` carries `target_paradigm` precisely because it is not
    inferable from content.

    A graph with no description is a hard error, never a fallback to the
    filename. That fallback is what made every prompt two words and every score
    uninterpretable; silently degrading to it again would be the same defect
    wearing the word "default".
    """
    from app.schemas.data_model import SynthesizedModel
    from scripts.conformance_prompts import DESCRIPTIONS, build_prompt

    out = []
    for path in sorted(GOLD.glob("*.json")):
        if path.name == "index.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        model = SynthesizedModel.model_validate(
            {
                "paradigm": raw["paradigm"],
                "entities": raw["entities"],
                "relationships": raw["relationships"],
            }
        )
        if path.stem not in DESCRIPTIONS:
            raise SystemExit(
                f"no conformance description for gold graph '{path.stem}'. Write "
                f"one to the calibration rule in scripts/conformance_prompts.py, "
                f"or exclude the graph with the reason recorded — never fall back "
                f"to the filename."
            )
        out.append(
            (path.stem, model, build_prompt(raw["paradigm"], DESCRIPTIONS[path.stem]))
        )
    return out


async def main(argv: list[str] | None = None) -> int:
    _refuse_unless_opted_in()

    from app.core.config import Settings
    from app.schemas.data_model import SynthesizedModel
    from app.services.llm_gateway import LLMGateway

    # The product's own system prompt, imported rather than restated so it
    # cannot drift from the one users actually get.
    from app.services.synthesis_engine import _SYSTEM_PROMPT
    from scripts.conformance_scoring import score_graph, verdict
    from scripts.conformance_threshold import (
        MAX_F1_DROP_VS_CLOUD,
        MAX_LINT_DELTA_VS_CLOUD,
        THRESHOLD_VERSION,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", required=True, help="comma-separated router provider names")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]
    gateway = LLMGateway(settings)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    graphs = _gold_graphs()

    rows = []
    verdicts = []
    # Every candidate graph, kept verbatim. The first run stored only scores,
    # so when the metric turned out to be measuring name agreement there was
    # nothing left to re-score: correcting the instrument meant paying for five
    # fresh provider calls whose outputs would differ anyway, and the two runs
    # could never be compared. A conformance number that cannot be recomputed
    # from preserved inputs is not reproducible, whatever the report says.
    captured: list[dict[str, object]] = []
    for provider in [p.strip() for p in args.providers.split(",") if p.strip()]:
        egress_class = gateway._egress_class(provider)
        model_identifier = gateway.providers[provider]["default_model"]
        scores = []
        for graph_id, gold, prompt in graphs:
            candidate: SynthesizedModel = await gateway.structured_completion(
                task="unstructured_doc_parsing",
                prompt=prompt,
                response_model=SynthesizedModel,
                # **The product's own system prompt, and its absence was a
                # defect that produced a published number.**
                #
                # This argument was omitted, `structured_completion` defaults it
                # to None, and the run therefore scored a bare model given a
                # domain description — not this product. None of the modelling
                # instructions reached the provider: not the Kimball rule that a
                # Fact -> Dimension edge must be N:1, not the 3NF bridge-table
                # rule, and not the omission guidance that exists precisely to
                # stop a model inventing governance terms.
                #
                # The 2026-09-02 run shows what that costs. Relationship F1 came
                # back at 0.013 with the cardinality rules unsent, and every
                # entity in the ecommerce candidate carried an invented tier —
                # the S5-2 defect, reproduced in full, because the paragraph
                # forbidding it was never sent. `MISSING_SLA` then fired on four
                # graphs and the report called it a systematic provider
                # behaviour, which it was not: it was ours.
                #
                # A conformance harness that does not send the product's prompt
                # measures the provider. That is a legitimate thing to measure
                # and it is not what D10 asks for.
                system_prompt=_SYSTEM_PROMPT,
                llm_override=provider,
            )
            captured.append(
                {
                    "gold_graph_id": graph_id,
                    "provider": provider,
                    "model_identifier": model_identifier,
                    # Recorded here so a later re-score is self-contained. These
                    # two are facts about the call, not about the metric, and
                    # `rescore_conformance` cannot reconstruct either: the first
                    # two candidate files omitted them, so re-scoring had to
                    # read them back out of the very report it was replacing.
                    "egress_class": egress_class,
                    "model_version": model_identifier,
                    "prompt_sha256": hashlib.sha256(
                        prompt.encode("utf-8")
                    ).hexdigest(),
                    "candidate": candidate.model_dump(mode="json"),
                }
            )
            scores.append(
                score_graph(
                    gold_graph_id=graph_id,
                    gold=gold,
                    candidate=candidate,
                    provider=provider,
                    egress_class=egress_class,
                    model_identifier=model_identifier,
                    # Providers do not reliably report a version distinct from
                    # the identifier; recording the identifier twice would be a
                    # fabricated distinction, so this is explicit.
                    model_version=model_identifier,
                    prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    run_started_at=started,
                )
            )
        rows.extend(scores)
        verdicts.append(verdict(scores))

    cloud = [v for v in verdicts if v.egress_class != "local"]
    best_cloud = max(cloud, key=lambda v: v.entity_f1, default=None)
    comparisons = []
    if best_cloud is not None:
        for v in verdicts:
            if v is best_cloud:
                continue
            drops = {
                "entity": best_cloud.entity_f1 - v.entity_f1,
                "column": best_cloud.column_f1 - v.column_f1,
                "relationship": best_cloud.relationship_f1 - v.relationship_f1,
            }
            worse = [k for k, d in drops.items() if d > MAX_F1_DROP_VS_CLOUD]
            if v.lint_delta - best_cloud.lint_delta > MAX_LINT_DELTA_VS_CLOUD:
                worse.append("lint")
            comparisons.append(
                {
                    "provider": v.provider,
                    "versus": best_cloud.provider,
                    "drops": {k: round(d, 4) for k, d in drops.items()},
                    "materially_worse_on": worse,
                }
            )

    def _round(value: float | None, places: int) -> float | None:
        """`None` means the axis did not apply — it is not a zero.

        Serialised as JSON null rather than a number, so a reader cannot mistake
        "no applicable graph" for a measured result.
        """
        return None if value is None else round(value, places)

    report = {
        "threshold_version": THRESHOLD_VERSION,
        "run_started_at": started,
        "providers": [
            {
                "provider": v.provider,
                "egress_class": v.egress_class,
                "model_identifier": v.model_identifier,
                "model_version": v.model_version,
                "entity_f1": _round(v.entity_f1, 4),
                "column_f1": _round(v.column_f1, 4),
                "relationship_f1": _round(v.relationship_f1, 4),
                "lint_delta_per_graph": round(v.lint_delta, 3),
                "systematic_new_codes": v.systematic_new_codes,
                "passed": v.passed,
                "failures": v.failures,
                "remedy": v.remedy,
            }
            for v in verdicts
        ],
        "materially_worse_than_cloud": comparisons,
        "per_graph": [
            {
                "gold_graph_id": s.gold_graph_id,
                "provider": s.provider,
                "entity_f1": _round(s.entity_f1, 4),
                "column_f1": _round(s.column_f1, 4),
                "relationship_f1": _round(s.relationship_f1, 4),
                "lint_delta": s.lint_delta,
                "new_codes": sorted(s.new_codes),
                "prompt_sha256": s.prompt_sha256,
                "model_identifier": s.model_identifier,
                "model_version": s.model_version,
            }
            for s in rows
        ],
    }
    candidates_path = args.out.with_suffix(".candidates.json")
    report["candidates_file"] = candidates_path.name

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    candidates_path.write_text(
        json.dumps({"run_started_at": started, "graphs": captured}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    print(f"wrote {candidates_path} ({len(captured)} candidate graphs)")
    for v in verdicts:
        print(f"  {v.provider}: {'PASS' if v.passed else 'FAIL'} {v.failures or ''}")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
