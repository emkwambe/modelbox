# ModelBox AI — v1.4.0 Release Notes

**Tag:** `v1.4.0`  ·  **Cut from:** `main`  ·  **CI:** green (Backend Pytest + Frontend `tsc`/build)

This release adds the **Business Requirements Library** — a curated gallery of
gold-standard reference architectures — on top of the completed v2.0 platform
(see [v1.3.0](RELEASE_NOTES_v1.3.0.md)). It solves the blank-canvas problem for
evaluators, gives ModelBox Trainer a set of pedagogical reference models, and
doubles as a standardized regression corpus for the synthesis engine and linter.

---

## Highlights

- **Business Requirements & Starter Template Library** — 5 domain scenarios, one
  per modeling paradigm, each with a natural-language prompt, a pre-built
  verified graph, and a modeling rationale.
- **Dual-mode launch** — synthesize live from the prompt, or hydrate a
  gold-standard graph instantly with zero LLM latency or token cost.
- **Trainer integration** — load reference architectures straight into the
  Socratic sandbox.

---

## Business Requirements Library

Accessible from the home prompt bar (**"📚 Explore Requirements Library"**) and
the Trainer header (**"📚 Library"**).

| Template | Paradigm | Key concepts |
|---|---|---|
| Subscription Analytics (SaaS) | Kimball | MRR/ARR facts, SCD Type 2 customer tiers, churn |
| E-Commerce & Logistics | Kimball | Order-line grain, degenerate dimension, basket analysis |
| Retail Banking & Ledger | Data Vault 2.0 | Hubs, Links, Satellites, immutable audit trail |
| Healthcare Patient EHR | 3NF | N:1 FK constraints, explicit PII/PHI tagging |
| Digital Marketing & Attribution | OBT | Multi-touch attribution, denormalized touchpoint grain |

### Dual-mode interactive launch

- **Mode A — Synthesize Live** — populates the natural-language prompt and
  paradigm selector so users can watch the LLM gateway turn requirements into a
  validated graph in real time.
- **Mode B — Inspect Gold-Standard Graph** — hydrates the pre-built
  `SynthesizedModel` directly onto the canvas with **no LLM call** (zero latency,
  zero tokens). Users immediately see entity types, primary-key badges, PII
  flags, topological validity, and can export DDL/dbt/Cube/contracts/semantic.

### Trainer launcher seam

The library is wired into `/trainer` (Mode B only), so instructors and learners
can drop a gold-standard reference architecture into the Spot-the-Flaw sandbox
alongside the Socratic tutor.

---

## Implementation notes

- **Frontend-only, no backend changes.** Templates live in a static registry
  (`frontend/src/lib/templates.ts`); the modal is `TemplateLibraryModal`.
- `canvasStore.loadGraph` gained an optional `paradigm` argument (backward
  compatible) so Mode B reflects the template's paradigm on the canvas.
- The card **Preview** expands to show each template's prompt and modeling
  rationale (the "how it was done" explainer).

## Housekeeping

- Appliance compose image tags bumped `v1.2.0` → `v1.3.0`.

## Known items / possible follow-ups

- Async-job-created models still default their `title` to `"Untitled Model"`.
- The rationale lives in the card Preview rather than a dedicated side-panel
  drawer (same content, lighter UI).

---

## Publishing

`release.yml` builds and pushes the backend + frontend images to GHCR on any
`v*` tag, tagged `1.4.0`, `1.4`, and `latest`. Cut the tag from green `main`:

```bash
git tag v1.4.0
git push origin v1.4.0
```
