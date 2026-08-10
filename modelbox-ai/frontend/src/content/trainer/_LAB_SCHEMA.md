# Trainer Lab JSON — schema

Runnable "Spot the Flaw" lab exercises. Each lab is a self-contained JSON file
in this directory. A lab's `graph` loads onto the `/canvas` (same shape as the
Requirements Library and `PUT /model/{id}/graph`); the student validates, fixes
the seeded flaws, and re-validates until clean. Flaws are graded by the **shipped
linter** (`GraphEngine.validate`), so labs stay in lock-step with the appliance.

```jsonc
{
  "id": "m1_lab1_grain_and_fanout",     // unique, matches filename
  "module": 1,                           // course module (1..4)
  "edition": "dimensional",              // dimensional | semantic | governance
  "title": "Spot the Flaw: Dimensional Edition",
  "difficulty": "beginner",              // beginner | intermediate | advanced
  "brief": "One-paragraph scenario shown to the learner.",

  // The flawed model. Same shape the canvas/PUT-graph consume.
  "graph": {
    "entities": [
      {
        "entity_name": "fact_sales",
        "entity_type": "FACT",           // TABLE | FACT | DIMENSION | HUB | LINK | SATELLITE
        "grain": "one row per sale line", // null to seed a MISSING_GRAIN flaw
        "description": "…",               // null/"" to seed a MISSING_DESCRIPTION flaw
        "columns": [
          {
            "name": "sale_id",
            "data_type": "INTEGER",
            "is_primary_key": true,
            "is_foreign_key": false,
            "is_pii": false,
            "is_metric": false,           // + "aggregation": "SUM" for a measure
            "description": "…"
          }
        ]
      }
    ],
    "relationships": [
      { "from": "fact_sales.customer_sk", "to": "dim_customer.customer_sk", "cardinality": "N:1" }
    ]
  },

  // The flaws the learner must resolve. `code` is the linter code the fix clears.
  "expected_flaws": [
    {
      "code": "MISSING_GRAIN",           // e.g. NAMING_CONVENTION | MISSING_GRAIN |
                                         // FAN_OUT_RISK | PII_EXPOSURE | MISSING_DESCRIPTION |
                                         // MISSING_PK | DANGLING_REF | ORPHAN_ENTITY
      "target": "fact_sales",            // entity or "a -> b" for a relationship
      "hint": "Short nudge (progressive).",
      "fix": "What a correct fix looks like."
    }
  ],

  "solution_notes": "Instructor-facing explanation of the ideal end state."
}
```

**Grading contract:** a lab is *solved* when re-validating the (student-edited)
graph produces **no issue whose `code` appears in `expected_flaws`**. Because the
grader is the shipped `GraphEngine.validate`, every seeded flaw must correspond to
a real lint code — verify a new lab with `GraphEngine.validate` before shipping it.
