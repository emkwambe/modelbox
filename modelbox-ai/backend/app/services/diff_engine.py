"""Schema diff engine (FR-2.2).

Compares two model graphs (V1 source -> V2 target) and emits dialect-specific
``ALTER``/``CREATE``/``DROP`` DDL plus a list of breaking changes. Pure and
deterministic — no DB or LLM dependency.
"""

from __future__ import annotations

import re

import sqlglot

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)

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

        # Modified entities (renames, adds, drops, type changes, key changes).
        for name, src_entity in src.items():
            tgt_entity = tgt.get(name)
            if tgt_entity is None:
                continue
            pairs, added, dropped = self._match_columns(
                src_entity.columns, tgt_entity.columns
            )

            for src_col, tgt_col in pairs:
                if src_col.name != tgt_col.name:
                    # A rename REPLACES the drop and the add. Emitting all
                    # three would satisfy any test looking for the keyword
                    # while still destroying the data (C4).
                    statements.append(
                        f"ALTER TABLE {name} RENAME COLUMN {src_col.name} "
                        f"TO {tgt_col.name}"
                    )

            for col in added:
                statements.append(
                    f"ALTER TABLE {name} ADD COLUMN {col.name} {col.data_type}"
                )

            for col in dropped:
                statements.append(f"ALTER TABLE {name} DROP COLUMN {col.name}")
                breaking.append(f"Dropped column: {name}.{col.name}")

            for src_col, tgt_col in pairs:
                if (
                    src_col.data_type.strip().upper()
                    != tgt_col.data_type.strip().upper()
                ):
                    statements.append(
                        f"ALTER TABLE {name} ALTER COLUMN {tgt_col.name} "
                        f"TYPE {tgt_col.data_type}"
                    )
                    breaking.append(
                        f"Type change: {name}.{tgt_col.name} "
                        f"{src_col.data_type} -> {tgt_col.data_type}"
                    )

            breaking.extend(
                self._key_breaks(name, src_entity, tgt_entity, pairs)
            )

        breaking.extend(self._relationship_breaks(source, target))

        transpiled = [self._transpile(s) for s in statements]
        semantic = self._semantic_breaks(source, target)
        return transpiled, breaking, semantic

    @staticmethod
    def _match_columns(
        src_cols: list[ColumnSchema], tgt_cols: list[ColumnSchema]
    ) -> tuple[
        list[tuple[ColumnSchema, ColumnSchema]],
        list[ColumnSchema],
        list[ColumnSchema],
    ]:
        """Pair source columns with target columns, by identity then by name.

        Returns ``(pairs, added, dropped)``. A pair whose two names differ is a
        rename, which is the whole of C4: the engine matched on name alone, so
        renaming a column looked like dropping one and adding another, and the
        emitted DDL destroyed its data.

        **Identity first, name second, and never anything else.** ``stable_id``
        is allocated by persistence, so a model straight from synthesis carries
        ``None`` on every column. Treating two ``None``s as equal — or pairing
        by position — would infer renames that never happened on every model
        the user has not saved yet, which is a worse failure than the one being
        fixed: a spurious RENAME silently discards a real ADD and DROP.
        """
        src_by_id = {c.stable_id: c for c in src_cols if c.stable_id is not None}
        tgt_by_id = {c.stable_id: c for c in tgt_cols if c.stable_id is not None}

        pairs: list[tuple[ColumnSchema, ColumnSchema]] = []
        matched_src: set[int] = set()
        matched_tgt: set[int] = set()

        for stable_id, src_col in src_by_id.items():
            tgt_col = tgt_by_id.get(stable_id)
            if tgt_col is not None:
                pairs.append((src_col, tgt_col))
                matched_src.add(id(src_col))
                matched_tgt.add(id(tgt_col))

        # Whatever identity could not pair — including everything on an unsaved
        # model — falls back to matching by name, which is exactly the old
        # behaviour and produces a drop plus an add for a rename.
        remaining_tgt = {
            c.name: c for c in tgt_cols if id(c) not in matched_tgt
        }
        for src_col in src_cols:
            if id(src_col) in matched_src:
                continue
            tgt_col = remaining_tgt.pop(src_col.name, None)
            if tgt_col is not None:
                pairs.append((src_col, tgt_col))
                matched_src.add(id(src_col))
                matched_tgt.add(id(tgt_col))

        dropped = [c for c in src_cols if id(c) not in matched_src]
        added = [c for c in tgt_cols if id(c) not in matched_tgt]
        return pairs, added, dropped

    @staticmethod
    def _key_breaks(
        name: str,
        src_entity: EntitySchema,
        tgt_entity: EntitySchema,
        pairs: list[tuple[ColumnSchema, ColumnSchema]],
    ) -> list[str]:
        """Report a changed primary key (M2).

        Compared as a set of *target* names so a rename is not mistaken for a
        re-key: renaming the PK column leaves the key on the same column, and
        reporting that as breaking would make every rename look destructive
        again through a different door.
        """
        renamed = {s.name: t.name for s, t in pairs}
        src_pk = {
            renamed.get(c.name, c.name)
            for c in src_entity.columns
            if c.is_primary_key
        }
        tgt_pk = {c.name for c in tgt_entity.columns if c.is_primary_key}
        if src_pk == tgt_pk:
            return []
        before = ", ".join(sorted(src_pk)) or "none"
        after = ", ".join(sorted(tgt_pk)) or "none"
        return [f"Primary key change: {name} ({before} -> {after})"]

    @staticmethod
    def _relationship_breaks(
        source: SynthesizedModel, target: SynthesizedModel
    ) -> list[str]:
        """Report removed foreign keys (C5).

        Removal only. Adding a relationship tightens a guarantee and breaks
        nothing downstream; reporting every difference would pass a removal
        test while crying wolf on each added join, which is how a diff earns
        being ignored.
        """
        def key(rel: RelationshipSchema) -> tuple[str, str]:
            return (rel.from_ref, rel.to_ref)

        target_keys = {key(r) for r in target.relationships}
        return [
            f"Removed foreign key: {rel.from_ref} -> {rel.to_ref}"
            for rel in source.relationships
            if key(rel) not in target_keys
        ]

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
