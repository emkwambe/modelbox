"""Schema diff engine (FR-2.2).

Compares two model graphs (V1 source -> V2 target) and emits dialect-specific
``ALTER``/``CREATE``/``DROP`` DDL plus a list of breaking changes. Pure and
deterministic — no DB or LLM dependency.
"""

from __future__ import annotations

import re

import sqlglot

from app.schemas.data_model import EntitySchema, SynthesizedModel

_SQLGLOT_DIALECTS: dict[str, str] = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "bigquery": "bigquery",
    "duckdb": "duckdb",
    "redshift": "redshift",
}


class DiffEngine:
    """Diffs two SynthesizedModel graphs into migration DDL."""

    def __init__(self, dialect: str = "postgres") -> None:
        self._dialect = _SQLGLOT_DIALECTS.get(dialect.lower(), "postgres")

    def diff(
        self, source: SynthesizedModel, target: SynthesizedModel
    ) -> tuple[list[str], list[str], list[str]]:
        """Return ``(alter_statements, breaking_changes, semantic_breaks)``."""
        src = {e.entity_name: e for e in source.entities}
        tgt = {e.entity_name: e for e in target.entities}

        statements: list[str] = []
        breaking: list[str] = []

        # Dropped entities (destructive).
        for name in src:
            if name not in tgt:
                statements.append(f"DROP TABLE {name} CASCADE")
                breaking.append(f"Dropped table: {name}")

        # Added entities.
        for name, entity in tgt.items():
            if name not in src:
                statements.append(self._create_table(entity))

        # Modified entities (column adds/drops/type changes).
        for name in src:
            if name not in tgt:
                continue
            src_cols = {c.name: c for c in src[name].columns}
            tgt_cols = {c.name: c for c in tgt[name].columns}

            for col_name, col in tgt_cols.items():
                if col_name not in src_cols:
                    statements.append(
                        f"ALTER TABLE {name} ADD COLUMN {col_name} {col.data_type}"
                    )

            for col_name in src_cols:
                if col_name not in tgt_cols:
                    statements.append(
                        f"ALTER TABLE {name} DROP COLUMN {col_name}"
                    )
                    breaking.append(f"Dropped column: {name}.{col_name}")

            for col_name, src_col in src_cols.items():
                tgt_col = tgt_cols.get(col_name)
                if tgt_col is None:
                    continue
                if src_col.data_type.strip().upper() != tgt_col.data_type.strip().upper():
                    statements.append(
                        f"ALTER TABLE {name} ALTER COLUMN {col_name} "
                        f"TYPE {tgt_col.data_type}"
                    )
                    breaking.append(
                        f"Type change: {name}.{col_name} "
                        f"{src_col.data_type} -> {tgt_col.data_type}"
                    )

        transpiled = [self._transpile(s) for s in statements]
        semantic = self._semantic_breaks(source, target)
        return transpiled, breaking, semantic

    def _semantic_breaks(
        self, source: SynthesizedModel, target: SynthesizedModel
    ) -> list[str]:
        """Flag physical changes that break an *in-model* semantic definition.

        A dropped/type-changed column is a semantic break when it is a declared
        measure (``is_metric``) or is referenced by a suggested-metric formula.
        In-model only — no external dashboard/consumer tracking.
        """
        tgt = {e.entity_name: e for e in target.entities}
        formulas = [(m.name, m.formula) for m in source.suggested_metrics]
        breaks: list[str] = []

        for entity in source.entities:
            name = entity.entity_name
            target_entity = tgt.get(name)

            # Whole entity dropped.
            if target_entity is None:
                for col in entity.columns:
                    if col.is_metric:
                        breaks.append(
                            f"Semantic break: dropped entity '{name}' removes "
                            f"declared measure '{col.name}'."
                        )
                for metric_name, formula in formulas:
                    if self._refs(formula, name):
                        breaks.append(
                            f"Semantic break: dropped entity '{name}' is "
                            f"referenced by metric '{metric_name}'."
                        )
                continue

            tgt_cols = {c.name: c for c in target_entity.columns}
            for col in entity.columns:
                dropped = col.name not in tgt_cols
                type_changed = (
                    not dropped
                    and col.data_type.strip().upper()
                    != tgt_cols[col.name].data_type.strip().upper()
                )
                if not (dropped or type_changed):
                    continue
                verb = "dropped" if dropped else "type-changed"
                if col.is_metric:
                    breaks.append(
                        f"Semantic break: {verb} column '{name}.{col.name}' is a "
                        f"declared measure (agg {col.aggregation or 'SUM'})."
                    )
                for metric_name, formula in formulas:
                    if self._refs(formula, name, col.name):
                        breaks.append(
                            f"Semantic break: {verb} column '{name}.{col.name}' is "
                            f"referenced by metric '{metric_name}'."
                        )
        return breaks

    @staticmethod
    def _refs(formula: str, entity: str, column: str | None = None) -> bool:
        """Whether a metric formula references an entity (and optional column)."""
        if column is None:
            return re.search(rf"\b{re.escape(entity)}\b", formula) is not None
        if f"{entity}.{column}" in formula:
            return True
        return re.search(rf"\b{re.escape(column)}\b", formula) is not None

    def _create_table(self, entity: EntitySchema) -> str:
        lines = [f"  {c.name} {c.data_type}" for c in entity.columns]
        pks = [c.name for c in entity.columns if c.is_primary_key]
        if pks:
            lines.append(f"  PRIMARY KEY ({', '.join(pks)})")
        return f"CREATE TABLE {entity.entity_name} (\n" + ",\n".join(lines) + "\n)"

    def _transpile(self, sql: str) -> str:
        try:
            out = sqlglot.transpile(sql, write=self._dialect)
            return (out[0] if out else sql) + ";"
        except Exception:  # noqa: BLE001 - fall back to raw DDL on parse failure
            return sql + ";"
