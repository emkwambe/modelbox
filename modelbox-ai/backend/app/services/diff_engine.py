"""Schema diff engine (FR-2.2).

Compares two model graphs (V1 source -> V2 target) and emits dialect-specific
``ALTER``/``CREATE``/``DROP`` DDL plus a list of breaking changes. Pure and
deterministic — no DB or LLM dependency.

**One comparison core** (Sprint 8 Step 5): :func:`compare` lists every
difference as a typed :class:`Change`, and both consumers read it — the
migration diff (:meth:`DiffEngine.diff`, whose output is unchanged) and the
drift report (``app.services.drift_report``). The two differ only in how
columns are paired: the migration diff pairs by ``stable_id`` first, so a
rename within one model's history is a rename; the drift report pairs by name
only, since a saved model and an imported file share no column identity, and
a rename it cannot see is a removal and an addition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)

#: Every kind of difference :func:`compare` reports.
CHANGE_KINDS = (
    "table_added", "table_removed", "column_added", "column_removed", "column_renamed",
    "type_changed", "declared_type_changed", "nullability_changed", "default_changed",
    "primary_key_changed", "unique_added", "unique_removed", "foreign_key_added", "foreign_key_removed",
    "check_added", "check_removed", "description_changed",
)


@dataclass(frozen=True)
class Change:
    """One difference between two graphs.

    ``column`` names a column-level change; ``columns`` the members of a
    constraint (key order for keys). ``before`` and ``after`` hold the two
    sides' values; ``detail`` what a reader needs beside them (the declared
    type texts, the referenced table).
    """

    kind: str
    table: str
    column: str | None = None
    columns: tuple[str, ...] = ()
    before: Any = None
    after: Any = None
    detail: dict[str, Any] = field(default_factory=dict)


def _norm_type(data_type: str) -> str:
    return data_type.strip().upper()


def _norm_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _pairs_by_name(src_cols: list[ColumnSchema], tgt_cols: list[ColumnSchema]) -> tuple[
        list[tuple[ColumnSchema, ColumnSchema]], list[ColumnSchema], list[ColumnSchema]]:
    """Pair by exact name only: never by identity, position or type."""
    tgt = {c.name: c for c in tgt_cols}
    pairs = [(c, tgt[c.name]) for c in src_cols if c.name in tgt]
    paired = {s.name for s, _ in pairs}
    return pairs, [c for c in tgt_cols if c.name not in paired], [c for c in src_cols if c.name not in paired]


def compare(source: SynthesizedModel, target: SynthesizedModel, *, identity: bool) -> list[Change]:
    """Every difference from ``source`` to ``target``, in a stable order.

    ``identity=True`` pairs columns by ``stable_id`` and then by name (the
    migration diff); ``identity=False`` by name only (the drift report), and
    then no ``column_renamed`` is ever reported.
    """
    src = {e.entity_name: e for e in source.entities}
    tgt = {e.entity_name: e for e in target.entities}
    changes: list[Change] = []
    changes += [Change("table_removed", name, before=entity) for name, entity in src.items() if name not in tgt]
    changes += [Change("table_added", name, after=entity) for name, entity in tgt.items() if name not in src]

    for name, src_entity in src.items():
        tgt_entity = tgt.get(name)
        if tgt_entity is None:
            continue
        if identity:
            pairs, added, dropped = DiffEngine._match_columns(src_entity.columns, tgt_entity.columns)
        else:
            pairs, added, dropped = _pairs_by_name(src_entity.columns, tgt_entity.columns)
        renamed = {s.name: t.name for s, t in pairs}

        changes += [Change("column_renamed", name, t.name, before=s.name, after=t.name)
                    for s, t in pairs if s.name != t.name]
        changes += [Change("column_added", name, col.name, after=col) for col in added]
        changes += [Change("column_removed", name, col.name, before=col) for col in dropped]

        for s, t in pairs:
            declared = {"declared_before": s.source_data_type, "declared_after": t.source_data_type}
            if _norm_type(s.data_type) != _norm_type(t.data_type):
                changes.append(Change("type_changed", name, t.name, before=s.data_type, after=t.data_type,
                                      detail=declared))
            elif s.source_data_type and t.source_data_type and \
                    _norm_text(s.source_data_type) != _norm_text(t.source_data_type):
                changes.append(Change("declared_type_changed", name, t.name, before=s.source_data_type,
                                      after=t.source_data_type, detail=declared))
            if s.is_nullable != t.is_nullable:
                changes.append(Change("nullability_changed", name, t.name, before=s.is_nullable,
                                      after=t.is_nullable))
            # Compared in the normalized form, shown in the original text
            # (Sprint 8 Step 3): a respelling is not a drift.
            if _norm_text(s.default_value) != _norm_text(t.default_value):
                changes.append(Change("default_changed", name, t.name,
                                      before=s.source_default_value or s.default_value,
                                      after=t.source_default_value or t.default_value))
            if _norm_text(s.description) != _norm_text(t.description):
                changes.append(Change("description_changed", name, t.name, before=s.description or None,
                                      after=t.description or None))

        def mapped(columns: list[str], renamed: dict[str, str] = renamed) -> tuple[str, ...]:
            return tuple(renamed.get(c, c) for c in columns)

        src_pk, tgt_pk = mapped(src_entity.primary_key), tuple(tgt_entity.primary_key)
        if src_pk != tgt_pk:
            changes.append(Change("primary_key_changed", name, columns=tgt_pk, before=list(src_pk),
                                  after=list(tgt_pk)))

        src_unique = {mapped(u.columns): u for u in src_entity.unique_constraints}
        tgt_unique = {tuple(u.columns): u for u in tgt_entity.unique_constraints}
        changes += [Change("unique_removed", name, columns=cols, before=src_unique[cols].name)
                    for cols in src_unique if cols not in tgt_unique]
        changes += [Change("unique_added", name, columns=cols, after=tgt_unique[cols].name)
                    for cols in tgt_unique if cols not in src_unique]

        def check_key(columns: tuple[str, ...], expression: str) -> tuple[tuple[str, ...], str]:
            return tuple(sorted(columns)), _norm_text(expression).lower()

        src_checks = {check_key(mapped(k.columns), k.expression): k for k in src_entity.check_constraints}
        tgt_checks = {check_key(tuple(k.columns), k.expression): k for k in tgt_entity.check_constraints}
        changes += [Change("check_removed", name, columns=tuple(src_checks[k].columns),
                           before=src_checks[k].expression) for k in src_checks if k not in tgt_checks]
        changes += [Change("check_added", name, columns=tuple(tgt_checks[k].columns),
                           after=tgt_checks[k].expression) for k in tgt_checks if k not in src_checks]

        if _norm_text(src_entity.description) != _norm_text(tgt_entity.description):
            changes.append(Change("description_changed", name, before=src_entity.description or None,
                                  after=tgt_entity.description or None))

    # Foreign keys, between tables both sides hold: a table added or removed
    # carries its keys with it, and that is its own change.
    def fk_key(rel: RelationshipSchema) -> tuple[str, tuple[str, ...], str, tuple[str, ...]]:
        return (rel.from_ref, tuple(rel.from_columns), rel.to_ref, tuple(rel.to_columns))

    def both_hold(rel: RelationshipSchema) -> bool:
        return rel.from_ref in src and rel.from_ref in tgt and rel.to_ref in src and rel.to_ref in tgt

    src_fks = {fk_key(r): r for r in source.relationships}
    tgt_fks = {fk_key(r): r for r in target.relationships}
    changes += [Change("foreign_key_removed", r.from_ref, columns=tuple(r.from_columns), before=r.name,
                       detail={"to": r.to_ref, "to_columns": list(r.to_columns), "all_tables_held": both_hold(r)})
                for k, r in src_fks.items() if k not in tgt_fks]
    changes += [Change("foreign_key_added", r.from_ref, columns=tuple(r.from_columns), after=r.name,
                       detail={"to": r.to_ref, "to_columns": list(r.to_columns), "all_tables_held": both_hold(r)})
                for k, r in tgt_fks.items() if k not in src_fks]
    return changes

_SQLGLOT_DIALECTS: dict[str, str] = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "bigquery": "bigquery",
    "duckdb": "duckdb",
    "redshift": "redshift",
}


@dataclass(frozen=True)
class MigrationDiff:
    """The migration diff: DDL, breaking changes, semantic breaks, and data loss."""

    statements: list[str]
    breaking: list[str]
    semantic: list[str]
    #: Every statement that destroys data, said in words: shown with the DDL.
    data_loss: list[str]


class DiffEngine:
    """Diffs two SynthesizedModel graphs into migration DDL."""

    def __init__(self, dialect: str = "postgres") -> None:
        self._dialect = _SQLGLOT_DIALECTS.get(dialect.lower(), "postgres")

    def diff(
        self, source: SynthesizedModel, target: SynthesizedModel, *, same_model: bool = False
    ) -> tuple[list[str], list[str], list[str]]:
        """Return ``(alter_statements, breaking_changes, semantic_breaks)``."""
        result = self.diff_report(source, target, same_model=same_model)
        return result.statements, result.breaking, result.semantic

    def diff_report(
        self, source: SynthesizedModel, target: SynthesizedModel, *, same_model: bool = False
    ) -> MigrationDiff:
        """The migration diff, rendered from :func:`compare`.

        **Columns are paired by internal id only between versions of the same
        model** (``same_model``). Every saved model numbers its columns from 1,
        so between two separately saved models equal ids name unrelated
        columns, and pairing by them turned an added column into a rename of
        another and dropped its data (Sprint 8 Step 5; owner decision, Step 6).
        Between separate models columns are paired by name, and a rename that
        is not certain is a removal plus an addition: the migration and
        ``data_loss`` say, for each, that the removed column's data is dropped.
        A destructive statement is never emitted on a guess.

        The migration diff states what DDL it emits and what it calls breaking,
        which is a subset of the changes: it does not migrate nullability,
        defaults, UNIQUE, CHECK or descriptions, and reports a primary key as
        changed only when its set of columns differs.
        """
        changes = compare(source, target, identity=same_model)

        def of(kind: str, table: str | None = None) -> list[Change]:
            return [c for c in changes if c.kind == kind and (table is None or c.table == table)]

        statements: list[str] = []
        breaking: list[str] = []
        # Statement index -> the data it destroys, stated above the statement.
        warnings: dict[int, str] = {}
        data_loss: list[str] = []
        renames_possible = not same_model

        def destroys(text: str) -> None:
            warnings[len(statements) - 1] = text
            data_loss.append(text)

        # Dropped entities (destructive).
        for change in of("table_removed"):
            statements.append(f"DROP TABLE {change.table} CASCADE")
            breaking.append(f"Dropped table: {change.table}")
            destroys(f"Drops table {change.table} and all of its data.")

        # Added entities.
        for change in of("table_added"):
            statements.append(self._create_table(change.after))

        # Modified entities (renames, adds, drops, type changes, key changes).
        target_names = {e.entity_name for e in target.entities}
        for name in (e.entity_name for e in source.entities if e.entity_name in target_names):
            # A rename REPLACES the drop and the add. Emitting all three would
            # satisfy any test looking for the keyword while still destroying
            # the data (C4).
            statements += [f"ALTER TABLE {name} RENAME COLUMN {c.before} TO {c.after}"
                           for c in of("column_renamed", name)]
            statements += [f"ALTER TABLE {name} ADD COLUMN {c.column} {c.after.data_type}"
                           for c in of("column_added", name)]
            for c in of("column_removed", name):
                statements.append(f"ALTER TABLE {name} DROP COLUMN {c.column}")
                breaking.append(f"Dropped column: {name}.{c.column}")
                destroys(
                    f"Drops column {name}.{c.column} and its data."
                    + (" Columns of separately saved models are matched by name, so a rename is a removal and"
                       " an addition: if this column was renamed, replace the DROP and the ADD with a RENAME."
                       if renames_possible else ""))
            for c in of("type_changed", name):
                statements.append(f"ALTER TABLE {name} ALTER COLUMN {c.column} TYPE {c.after}")
                breaking.append(f"Type change: {name}.{c.column} {c.before} -> {c.after}")
            breaking += self._key_breaks(name, of("primary_key_changed", name))

        breaking += self._relationship_breaks(of("foreign_key_removed"))

        transpiled = [self._transpile(s) for s in statements]
        # The warning goes into the migration itself, as a comment above the
        # statement, so it travels with the DDL wherever it is pasted.
        transpiled = [f"-- DATA LOSS: {warnings[i]}\n{sql}" if i in warnings else sql
                      for i, sql in enumerate(transpiled)]
        semantic = self._semantic_breaks(source, target)
        return MigrationDiff(transpiled, breaking, semantic, data_loss)

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
    def _key_breaks(name: str, changes: list[Change]) -> list[str]:
        """Report a changed primary key (M2).

        Compared as a set of *target* names so a rename is not mistaken for a
        re-key: renaming the PK column leaves the key on the same column, and
        reporting that as breaking would make every rename look destructive
        again through a different door. (:func:`compare` has already mapped
        the source key through the renames.)
        """
        breaks = []
        for change in changes:
            before, after = set(change.before), set(change.after)
            if before != after:
                breaks.append(f"Primary key change: {name} ({', '.join(sorted(before)) or 'none'} -> "
                              f"{', '.join(sorted(after)) or 'none'})")
        return breaks

    @staticmethod
    def _relationship_breaks(removed: list[Change]) -> list[str]:
        """Report removed foreign keys (C5).

        Removal only. Adding a relationship tightens a guarantee and breaks
        nothing downstream; reporting every difference would pass a removal
        test while crying wolf on each added join, which is how a diff earns
        being ignored.
        """
        def label(entity: str, columns: list[str]) -> str:
            if len(columns) == 1:
                return f"{entity}.{columns[0]}"
            return f"{entity}({', '.join(columns)})" if columns else entity

        return [
            f"Removed foreign key: {label(c.table, list(c.columns))} -> {label(c.detail['to'], c.detail['to_columns'])}"
            for c in removed
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
