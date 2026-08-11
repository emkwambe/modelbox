# Synthetic defect-reproduction fixtures

These are **not** gold graphs. The five models in `../gold/` are extracted from
the Requirements Library (`frontend/src/lib/templates.ts`) and serve double duty
as a curriculum and marketing asset — they are deliberately *correct*, and
seeding them with defects would cost more than it saves.

Three audit findings cannot be reproduced on a correct model:

| Fixture | Finding | Why the gold graphs cannot express it |
|---|---|---|
| `quality_rules.json` | H1, M7 | No gold graph declares `min_value` / `max_value` / `regex_pattern`, so neither the seed generator's disregard for them nor the missing `packages.yml` is reachable. |
| `role_playing_dimension.json` | B1 | In every gold graph the FK column name coincidentally equals the parent's PK column name, so MetricFlow's foreign-entity naming lines up by luck. A role-playing dimension (`ship_to_` / `bill_to_`) is the ordinary Kimball case that breaks it. |
| `spaced_title.json` | H6 | Every gold graph `id` is already a safe identifier, so the unsanitised Protobuf **filename** (as opposed to the package name, which *is* sanitised) never surfaces. |

## Shape

Identical to `../gold/*.json` so a fixture can graduate into the Requirements
Library if it ever becomes a teaching asset, plus two fields:

- `defect` — the audit finding ID this fixture reproduces.
- `rationale` — what a correct emitter would do instead.
- `dataset_name` *(optional)* — overrides the export dataset name, for defects
  that live in artifact naming rather than in the graph.

`role_playing_dimension.json` is a Sprint 8 Trainer lab candidate: a real
defect, a real parser error, and a verifiable fix.
