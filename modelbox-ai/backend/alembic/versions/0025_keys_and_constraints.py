"""Keys and constraints get one source: their own tables, not column flags.

Sprint 8 Step 3 (owner decisions, 2026-09-29). Until now a primary key, a
UNIQUE or CHECK constraint and a foreign key were flags on
`entity_columns` (`is_primary_key`, `is_unique`, `check_expression`,
`is_foreign_key`, `reference_target`), plus an optional column id at each end
of a relationship. A composite foreign key, or a UNIQUE or CHECK over several
columns, could not be stored at all.

After this migration:

* `entity_constraints` holds each entity's PRIMARY KEY, UNIQUE and CHECK
  constraints, and `entity_constraint_columns` their columns in order;
* `relationship_columns` holds each relationship's column pairs, in order, by
  column name; a relationship with none is unresolved;
* `model_entities.position` and `entity_relationships.position` keep a model's
  order, and `entity_relationships.name` a foreign key's name;
* the five column flags and the two relationship column ids are dropped;
* `entity_columns.source_default_value` holds an imported column's DEFAULT
  exactly as the file declared it, beside the normalized `default_value`, as
  0024 did for types (nullable, no backfill).

The conversion, per model:

* the columns flagged `is_primary_key`, in ordinal order, become the entity's
  primary key; each `is_unique` column a one-column UNIQUE; each
  `check_expression` a one-column CHECK. Exact.
* a relationship's two column ids become one column pair. A relationship
  with neither is kept unresolved, and one with only one end is kept with that
  end: both are listed.
* a `reference_target` that a relationship from the same column already
  states is dropped as a duplicate. One that no relationship backs becomes an
  N:1 relationship when its entity is in the model, and is listed; one whose
  entity is not in the model, or that contradicts the column's relationship,
  cannot be kept in the model and is listed with its text.
* an `is_foreign_key` flag with no relationship and no reference names no
  target; it is listed.

Everything listed goes to `model_conversion_findings`, by model, and is served
with the model. Nothing is dropped silently.

The downgrade restores what the older schema can hold: the flags from
one-column constraints and the first column pair of each relationship. A
composite key, or a UNIQUE or CHECK over several columns, has no place there.

Revision ID: 0025_keys_and_constraints
Revises: 0024_column_source_type
"""

from __future__ import annotations

import uuid
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision: str = "0025_keys_and_constraints"
down_revision: str | None = "0024_column_source_type"
branch_labels: str | None = None
depends_on: str | None = None

REVISION = revision


def _create_tables() -> None:
    op.create_table(
        "entity_constraints",
        sa.Column("constraint_id", sa.Uuid(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_id", sa.Uuid(),
                  sa.ForeignKey("model_entities.entity_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("expression", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('PRIMARY KEY', 'UNIQUE', 'CHECK')", name="ck_entity_constraints_kind"),
        sa.CheckConstraint("(kind = 'CHECK') = (expression IS NOT NULL)",
                           name="ck_entity_constraints_expression"),
    )
    op.create_index("ix_entity_constraints_entity_id", "entity_constraints", ["entity_id"])
    op.create_table(
        "entity_constraint_columns",
        sa.Column("constraint_id", sa.Uuid(),
                  sa.ForeignKey("entity_constraints.constraint_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("column_name", sa.String(128), nullable=False),
    )
    op.create_table(
        "relationship_columns",
        sa.Column("relationship_id", sa.Uuid(),
                  sa.ForeignKey("entity_relationships.relationship_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("from_column_name", sa.String(128), nullable=True),
        sa.Column("to_column_name", sa.String(128), nullable=True),
    )
    op.create_table(
        "model_conversion_findings",
        sa.Column("finding_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_id", sa.Uuid(),
                  sa.ForeignKey("data_models.model_id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("entity_name", sa.String(128), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    op.create_index("ix_model_conversion_findings_model_id", "model_conversion_findings", ["model_id"])
    op.add_column("model_entities", sa.Column("position", sa.Integer(), nullable=False,
                                              server_default=sa.text("0")))
    op.add_column("entity_relationships", sa.Column("position", sa.Integer(), nullable=False,
                                                    server_default=sa.text("0")))
    op.add_column("entity_relationships", sa.Column("name", sa.String(128), nullable=True))
    op.add_column("entity_columns", sa.Column("source_default_value", sa.Text(), nullable=True))


def upgrade() -> None:
    _create_tables()
    bind = op.get_bind()

    entities = bind.execute(sa.text(
        "SELECT entity_id, model_id, entity_name FROM model_entities ORDER BY model_id, entity_name")).all()
    entity_name = {e.entity_id: e.entity_name for e in entities}
    entity_model = {e.entity_id: e.model_id for e in entities}
    by_model_name = {(e.model_id, e.entity_name): e.entity_id for e in entities}
    order: dict[uuid.UUID, int] = defaultdict(int)
    for e in entities:
        bind.execute(sa.text("UPDATE model_entities SET position = :p WHERE entity_id = :e"),
                     {"p": order[e.model_id], "e": e.entity_id})
        order[e.model_id] += 1

    columns = bind.execute(sa.text(
        "SELECT column_id, entity_id, column_name, ordinal_position, is_primary_key, is_foreign_key, "
        "is_unique, check_expression, reference_target FROM entity_columns "
        "ORDER BY entity_id, ordinal_position, column_name")).all()
    column_name = {c.column_id: c.column_name for c in columns}
    columns_of: dict[uuid.UUID, set[str]] = defaultdict(set)
    for c in columns:
        columns_of[c.entity_id].add(c.column_name)

    def finding(model_id: uuid.UUID, kind: str, entity: str | None, detail: str) -> None:
        bind.execute(sa.text(
            "INSERT INTO model_conversion_findings (finding_id, model_id, revision, kind, entity_name, detail) "
            "VALUES (:f, :m, :r, :k, :e, :d)"),
            {"f": uuid.uuid4(), "m": model_id, "r": REVISION, "k": kind, "e": entity, "d": detail})

    def constraint(entity_id: uuid.UUID, kind: str, expression: str | None, members: list[str],
                   position: int) -> None:
        constraint_id = uuid.uuid4()
        bind.execute(sa.text(
            "INSERT INTO entity_constraints (constraint_id, entity_id, kind, name, expression, position) "
            "VALUES (:c, :e, :k, NULL, :x, :p)"),
            {"c": constraint_id, "e": entity_id, "k": kind, "x": expression, "p": position})
        for i, member in enumerate(members):
            bind.execute(sa.text(
                "INSERT INTO entity_constraint_columns (constraint_id, position, column_name) VALUES (:c, :p, :n)"),
                {"c": constraint_id, "p": i, "n": member})

    # Primary keys, UNIQUE and CHECK: exact.
    by_entity: dict[uuid.UUID, list] = defaultdict(list)
    for c in columns:
        by_entity[c.entity_id].append(c)
    for entity_id, cols in by_entity.items():
        position = 0
        key = [c.column_name for c in cols if c.is_primary_key]
        if key:
            constraint(entity_id, "PRIMARY KEY", None, key, position)
            position += 1
        for c in cols:
            if c.is_unique:
                constraint(entity_id, "UNIQUE", None, [c.column_name], position)
                position += 1
        for c in cols:
            if c.check_expression:
                constraint(entity_id, "CHECK", c.check_expression, [c.column_name], position)
                position += 1

    # Relationships: their column ids become one named pair.
    relationships = bind.execute(sa.text(
        "SELECT relationship_id, model_id, from_entity_id, from_column_id, to_entity_id, to_column_id "
        "FROM entity_relationships ORDER BY model_id, relationship_id")).all()
    rel_order: dict[uuid.UUID, int] = defaultdict(int)
    stated: dict[tuple[uuid.UUID, str], str | None] = {}  # (from entity, column) -> "entity.column" target
    for r in relationships:
        bind.execute(sa.text("UPDATE entity_relationships SET position = :p WHERE relationship_id = :r"),
                     {"p": rel_order[r.model_id], "r": r.relationship_id})
        rel_order[r.model_id] += 1
        from_column = column_name.get(r.from_column_id) if r.from_column_id else None
        to_column = column_name.get(r.to_column_id) if r.to_column_id else None
        ends = f"{entity_name[r.from_entity_id]} -> {entity_name[r.to_entity_id]}"
        if from_column is None and to_column is None:
            finding(r.model_id, "unresolved_relationship", entity_name[r.from_entity_id],
                    f"{ends}: saved without columns; kept unresolved until its columns are chosen")
            continue
        bind.execute(sa.text(
            "INSERT INTO relationship_columns (relationship_id, position, from_column_name, to_column_name) "
            "VALUES (:r, 0, :f, :t)"), {"r": r.relationship_id, "f": from_column, "t": to_column})
        if from_column is None or to_column is None:
            finding(r.model_id, "partly_resolved_relationship", entity_name[r.from_entity_id],
                    f"{ends}: saved with only its {'referencing' if from_column else 'referenced'} column "
                    f"({from_column or to_column}); kept with that column")
        if from_column is not None:
            stated[(r.from_entity_id, from_column)] = (
                f"{entity_name[r.to_entity_id]}.{to_column}" if to_column else entity_name[r.to_entity_id])

    # References and foreign-key flags: backed, converted, or listed.
    for c in columns:
        model_id = entity_model[c.entity_id]
        here = f"{entity_name[c.entity_id]}.{c.column_name}"
        backed = stated.get((c.entity_id, c.column_name), False)
        if c.reference_target:
            if backed is not False:
                if backed != c.reference_target:
                    finding(model_id, "reference_contradicts_relationship", entity_name[c.entity_id],
                            f"{here} references {c.reference_target!r}, but its relationship targets "
                            f"{backed!r}; the relationship is kept")
                continue
            target_entity, _, target_column = c.reference_target.partition(".")
            target_id = by_model_name.get((model_id, target_entity))
            if target_id is None:
                finding(model_id, "reference_target_missing", entity_name[c.entity_id],
                        f"{here} references {c.reference_target!r}, which is not an entity in this model")
                continue
            relationship_id = uuid.uuid4()
            bind.execute(sa.text(
                "INSERT INTO entity_relationships (relationship_id, model_id, from_entity_id, to_entity_id, "
                "cardinality, position) VALUES (:r, :m, :f, :t, 'N:1', :p)"),
                {"r": relationship_id, "m": model_id, "f": c.entity_id, "t": target_id, "p": rel_order[model_id]})
            rel_order[model_id] += 1
            bind.execute(sa.text(
                "INSERT INTO relationship_columns (relationship_id, position, from_column_name, to_column_name) "
                "VALUES (:r, 0, :f, :t)"),
                {"r": relationship_id, "f": c.column_name, "t": target_column or None})
            missing = target_column and target_column not in columns_of[target_id]
            finding(model_id, "reference_became_relationship", entity_name[c.entity_id],
                    f"{here} references {c.reference_target!r}, which no relationship stated; now an N:1 "
                    f"relationship" + (" naming a column the target does not have" if missing else ""))
        elif c.is_foreign_key and backed is False:
            finding(model_id, "foreign_key_without_target", entity_name[c.entity_id],
                    f"{here} was flagged as a foreign key with no relationship or reference naming its target")

    with op.batch_alter_table("entity_relationships") as batch:
        batch.drop_column("from_column_id")
        batch.drop_column("to_column_id")
    with op.batch_alter_table("entity_columns") as batch:
        for name in ("is_primary_key", "is_foreign_key", "is_unique", "check_expression", "reference_target"):
            batch.drop_column(name)


def downgrade() -> None:
    with op.batch_alter_table("entity_columns") as batch:
        batch.add_column(sa.Column("is_primary_key", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.add_column(sa.Column("is_foreign_key", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.add_column(sa.Column("is_unique", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.add_column(sa.Column("check_expression", sa.String(512), nullable=True))
        batch.add_column(sa.Column("reference_target", sa.String(257), nullable=True))
    with op.batch_alter_table("entity_relationships") as batch:
        batch.add_column(sa.Column("from_column_id", sa.Uuid(), sa.ForeignKey("entity_columns.column_id"),
                                   nullable=True))
        batch.add_column(sa.Column("to_column_id", sa.Uuid(), sa.ForeignKey("entity_columns.column_id"),
                                   nullable=True))
    bind = op.get_bind()
    column_id = {(r.entity_id, r.column_name): r.column_id for r in bind.execute(sa.text(
        "SELECT column_id, entity_id, column_name FROM entity_columns")).all()}

    members = bind.execute(sa.text(
        "SELECT c.entity_id, c.kind, c.expression, c.constraint_id, m.column_name, "
        "(SELECT count(*) FROM entity_constraint_columns n WHERE n.constraint_id = c.constraint_id) AS width "
        "FROM entity_constraints c JOIN entity_constraint_columns m ON m.constraint_id = c.constraint_id")).all()
    for m in members:
        target = column_id.get((m.entity_id, m.column_name))
        if target is None:
            continue
        if m.kind == "PRIMARY KEY":
            bind.execute(sa.text("UPDATE entity_columns SET is_primary_key = true WHERE column_id = :c"),
                         {"c": target})
        elif m.width == 1 and m.kind == "UNIQUE":
            bind.execute(sa.text("UPDATE entity_columns SET is_unique = true WHERE column_id = :c"), {"c": target})
        elif m.width == 1 and m.kind == "CHECK":
            bind.execute(sa.text(
                "UPDATE entity_columns SET check_expression = CASE WHEN check_expression IS NULL "
                "THEN CAST(:x AS TEXT) ELSE '(' || check_expression || ') AND (' || CAST(:x AS TEXT) || ')' END "
                "WHERE column_id = :c"),
                {"c": target, "x": m.expression})

    pairs = bind.execute(sa.text(
        "SELECT r.relationship_id, r.from_entity_id, r.to_entity_id, p.from_column_name, p.to_column_name, "
        "t.entity_name AS to_entity FROM entity_relationships r "
        "JOIN relationship_columns p ON p.relationship_id = r.relationship_id AND p.position = 0 "
        "JOIN model_entities t ON t.entity_id = r.to_entity_id")).all()
    for p in pairs:
        source = column_id.get((p.from_entity_id, p.from_column_name))
        bind.execute(sa.text(
            "UPDATE entity_relationships SET from_column_id = :f, to_column_id = :t WHERE relationship_id = :r"),
            {"f": source, "t": column_id.get((p.to_entity_id, p.to_column_name)), "r": p.relationship_id})
        if source is not None:
            bind.execute(sa.text(
                "UPDATE entity_columns SET is_foreign_key = true, reference_target = :x WHERE column_id = :c"),
                {"c": source, "x": f"{p.to_entity}.{p.to_column_name}" if p.to_column_name else p.to_entity})

    op.drop_column("entity_columns", "source_default_value")
    op.drop_column("entity_relationships", "name")
    op.drop_column("entity_relationships", "position")
    op.drop_column("model_entities", "position")
    op.drop_index("ix_model_conversion_findings_model_id", table_name="model_conversion_findings")
    op.drop_table("model_conversion_findings")
    op.drop_table("relationship_columns")
    op.drop_table("entity_constraint_columns")
    op.drop_index("ix_entity_constraints_entity_id", table_name="entity_constraints")
    op.drop_table("entity_constraints")
