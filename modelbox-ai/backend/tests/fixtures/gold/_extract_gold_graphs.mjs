/**
 * Regenerates the gold-graph JSON mirror from the Requirements Library.
 *
 * `frontend/src/lib/templates.ts` is the single source of truth for the five
 * gold graphs. The artifact-fidelity harness needs them in Python, and
 * transcribing them by hand would be exactly the kind of drift this sprint
 * exists to eliminate — so they are extracted mechanically instead.
 *
 * Run:  node --experimental-strip-types _extract_gold_graphs.mjs [outDir]
 *
 * `outDir` defaults to this directory. The drift guard passes a temporary
 * directory instead, so it can diff a fresh extraction against the committed
 * mirror without touching it.
 *
 * The emitted JSON is committed so the harness runs with no Node dependency.
 * `test_artifact_fidelity.py::test_gold_mirror_matches_templates_ts` re-runs
 * this and asserts equality, so the mirror can never silently fall behind.
 */
import { writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = process.argv[2] ? resolve(process.argv[2]) : here;
const templatesPath = join(here, '..', '..', '..', '..', 'frontend', 'src', 'lib', 'templates.ts');

const { TEMPLATES } = await import(pathToFileURL(templatesPath).href);

/** Project a template onto the SynthesizedModel shape the backend consumes. */
function toGraph(t) {
  return {
    id: t.id,
    title: t.title,
    paradigm: t.paradigm,
    entities: t.entities.map((e) => ({
      entity_name: e.entity_name,
      entity_type: e.entity_type,
      description: e.description ?? null,
      grain: e.grain ?? null,
      tier: e.tier ?? null,
      freshness_sla: e.freshness_sla ?? null,
      agg_time_column: e.agg_time_column ?? null,
      canvas_position_x: e.canvas_position_x ?? 0,
      canvas_position_y: e.canvas_position_y ?? 0,
      columns: e.columns.map((c) => ({
        name: c.name,
        data_type: c.data_type,
        is_primary_key: c.is_primary_key ?? false,
        is_foreign_key: c.is_foreign_key ?? false,
        is_pii: c.is_pii ?? false,
        pii_type: c.pii_type ?? null,
        description: c.description ?? null,
        references: c.references ?? null,
        is_metric: c.is_metric ?? false,
        aggregation: c.aggregation ?? null,
        min_value: c.min_value ?? null,
        max_value: c.max_value ?? null,
        regex_pattern: c.regex_pattern ?? null,
        // Sprint 2 physical constraints are emitted only when a template
        // actually sets them. Writing `is_nullable: true` for every column
        // would put a claim in the fixture that the template never made, and
        // would contradict the IR for primary keys, which are forced
        // non-nullable. Absent means "the IR default applies".
        ...(c.is_nullable === undefined ? {} : { is_nullable: c.is_nullable }),
        ...(c.is_unique === undefined ? {} : { is_unique: c.is_unique }),
        ...(c.default_value == null ? {} : { default_value: c.default_value }),
        ...(c.check_expression == null
          ? {}
          : { check_expression: c.check_expression }),
      })),
    })),
    relationships: t.relationships.map((r) => ({
      from: r.from,
      to: r.to,
      cardinality: r.cardinality,
    })),
  };
}

const index = [];
for (const template of TEMPLATES) {
  const graph = toGraph(template);
  writeFileSync(join(outDir, `${graph.id}.json`), JSON.stringify(graph, null, 2) + '\n', 'utf8');
  index.push(graph.id);
}
writeFileSync(join(outDir, 'index.json'), JSON.stringify(index, null, 2) + '\n', 'utf8');
console.log(`wrote ${index.length} gold graphs: ${index.join(', ')}`);
