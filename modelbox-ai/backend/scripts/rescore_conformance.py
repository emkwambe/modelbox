"""Re-score a conformance run from its preserved candidates (D10).

The runner captures every candidate graph verbatim precisely so a metric change
can be applied to the same outputs without paying for the calls again. That
affordance exists because the *first* run did not have it: when the metric
turned out to be measuring name agreement, there was nothing left to re-score,
and correcting the instrument meant buying six fresh calls whose outputs would
differ anyway — so the before and after could never be compared.

This is that affordance being used. No provider is contacted; the only thing
that changes between the original report and this one is the scoring code.

**Every re-scored report says so, in the file.** `rescored` carries the date and
the reason, and `run_started_at` keeps the *original* run's timestamp rather
than today's, because the answer to "when did these calls happen" is unchanged
by re-scoring them. A regenerated report that looked like a fresh run would be a
worse lie than a stale one: stale numbers are merely old, and a re-score
presented as a run invents provider calls that never happened.

Usage:
    .venv/Scripts/python -m scripts.rescore_conformance \\
        --candidates ../docs/marketing/conformance-report.candidates.json \\
        --out ../docs/marketing/conformance-report.json \\
        --reason "entity matcher: Jaccard -> overlap coefficient"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_GOLD = _BACKEND / "tests" / "fixtures" / "gold"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--reason",
        required=True,
        help="What changed in the scoring, recorded in the report.",
    )
    args = parser.parse_args()

    from app.schemas.data_model import SynthesizedModel
    from scripts.conformance_scoring import score_graph, verdict
    from scripts.conformance_threshold import (
        MAX_F1_DROP_VS_CLOUD,
        MAX_LINT_DELTA_VS_CLOUD,
        THRESHOLD_VERSION,
    )

    captured = json.loads(args.candidates.read_text(encoding="utf-8"))
    graphs = captured["graphs"]
    if not graphs:
        print("refusing to write: the candidates file holds no graphs")
        return 1

    # Egress class is a property of the call, not of the scoring, and older
    # candidate files do not carry it. The report being replaced does, and it is
    # the record of that run — so read it from there rather than assuming
    # "cloud". A local provider re-scored under a hardcoded default would be
    # published as cloud egress, which is a compliance claim, not a rounding
    # error. The runner now records it in the candidates too; this path stays
    # for the two files written before it did.
    if not args.out.exists():
        print(f"refusing to write: {args.out} does not exist, so there is no "
              "record of the egress class these calls actually had")
        return 1
    prior = json.loads(args.out.read_text(encoding="utf-8"))
    prior_by_provider = {p["provider"]: p for p in prior["providers"]}

    def _provenance(entry: dict, key: str) -> str:
        if key in entry:
            return entry[key]
        record = prior_by_provider.get(entry["provider"])
        if record is None or key not in record:
            raise SystemExit(
                f"refusing to write: {key!r} for provider "
                f"{entry['provider']!r} is in neither the candidates file nor "
                f"the prior report. It is a fact about the run and cannot be "
                f"reconstructed from the scoring."
            )
        return record[key]

    rows = []
    for entry in graphs:
        gold_raw = json.loads(
            (_GOLD / f"{entry['gold_graph_id']}.json").read_text(encoding="utf-8")
        )
        gold = SynthesizedModel(
            paradigm=gold_raw["paradigm"],
            entities=gold_raw["entities"],
            relationships=gold_raw["relationships"],
        )
        rows.append(
            score_graph(
                gold_graph_id=entry["gold_graph_id"],
                gold=gold,
                candidate=SynthesizedModel(**entry["candidate"]),
                provider=entry["provider"],
                egress_class=_provenance(entry, "egress_class"),
                model_identifier=entry["model_identifier"],
                model_version=_provenance(entry, "model_version"),
                prompt_sha256=entry["prompt_sha256"],
                run_started_at=captured["run_started_at"],
            )
        )

    verdicts = [verdict([r for r in rows if r.provider == p]) for p in
                dict.fromkeys(r.provider for r in rows)]

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
        """`None` means the axis did not apply — it is not a zero."""
        return None if value is None else round(value, places)

    report = {
        "threshold_version": THRESHOLD_VERSION,
        # The original call time, deliberately. Re-scoring does not move it.
        "run_started_at": captured["run_started_at"],
        "rescored": {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "reason": args.reason,
            "from_candidates": args.candidates.name,
            "note": (
                "No provider was contacted. These scores come from the candidate "
                "graphs captured during the run above, re-scored with the current "
                "metric."
            ),
        },
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
        "candidates_file": args.candidates.name,
    }

    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {args.out} (re-scored from {len(graphs)} preserved candidates)")
    for v in verdicts:
        print(f"  {v.provider}: {'PASS' if v.passed else 'FAIL'} {v.failures or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
