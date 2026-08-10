"""Database introspection service (FR-2.1).

Reads an existing database's ``INFORMATION_SCHEMA`` and constructs a
``SynthesizedModel`` graph ready for GraphEngine linting and paradigm
transformation. The metadata->graph mapping is a pure function
(:meth:`build_graph`) so it is fully unit-testable without a live database.
"""

from __future__ import annotations

from typing import Any

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)

# information_schema.data_type -> normalized ModelBox/SQLGlot-friendly type.
_PG_TYPE_MAP: dict[str, str] = {
    "character varying": "VARCHAR",
    "character": "CHAR",
    "text": "TEXT",
    "integer": "INT",
    "bigint": "BIGINT",
    "smallint": "SMALLINT",
    "numeric": "NUMERIC",
    "real": "REAL",
    "double precision": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMPTZ",
    "uuid": "UUID",
    "jsonb": "JSONB",
    "json": "JSON",
}


def _map_type(data_type: str) -> str:
    return _PG_TYPE_MAP.get(data_type.lower(), data_type.upper())


class IntrospectionService:
    """Introspects physical schemas into ModelBox graphs."""

    @staticmethod
    def build_graph(
        tables: list[str],
        columns: list[dict[str, Any]],
        primary_keys: set[tuple[str, str]],
        foreign_keys: list[dict[str, str]],
    ) -> SynthesizedModel:
        """Pure mapping of DB metadata -> a 3NF ``SynthesizedModel``.

        Entity type is inferred from FK topology: >=2 outgoing FKs -> FACT;
        referenced with <=1 outgoing -> DIMENSION; otherwise TABLE.
        """
        cols_by_table: dict[str, list[dict[str, Any]]] = {}
        for col in columns:
            cols_by_table.setdefault(col["table"], []).append(col)

        out_fk: dict[str, int] = {}
        in_ref: dict[str, int] = {}
        fk_cols: set[tuple[str, str]] = set()
        for fk in foreign_keys:
            out_fk[fk["from_table"]] = out_fk.get(fk["from_table"], 0) + 1
            in_ref[fk["to_table"]] = in_ref.get(fk["to_table"], 0) + 1
            fk_cols.add((fk["from_table"], fk["from_column"]))

        entities: list[EntitySchema] = []
        for table in tables:
            table_cols = sorted(
                cols_by_table.get(table, []),
                key=lambda c: c.get("ordinal") or 0,
            )
            schema_cols = [
                ColumnSchema(
                    name=col["column"],
                    data_type=_map_type(col["data_type"]),
                    is_primary_key=(table, col["column"]) in primary_keys,
                    is_foreign_key=(table, col["column"]) in fk_cols,
                    ordinal_position=col.get("ordinal"),
                )
                for col in table_cols
            ]
            if not schema_cols:
                continue
            out = out_fk.get(table, 0)
            inc = in_ref.get(table, 0)
            entity_type = (
                "FACT"
                if out >= 2
                else "DIMENSION"
                if inc >= 1 and out <= 1
                else "TABLE"
            )
            entities.append(
                EntitySchema(
                    entity_name=table,
                    entity_type=entity_type,  # type: ignore[arg-type]
                    columns=schema_cols,
                )
            )

        relationships = [
            RelationshipSchema.model_validate(
                {
                    "from": f"{fk['from_table']}.{fk['from_column']}",
                    "to": f"{fk['to_table']}.{fk['to_column']}",
                    "cardinality": "N:1",
                }
            )
            for fk in foreign_keys
        ]

        return SynthesizedModel(
            paradigm="3NF",  # type: ignore[arg-type]
            entities=entities,
            relationships=relationships,
        )

    @staticmethod
    async def introspect_postgresql(
        connection_uri: str, schema_name: str = "public"
    ) -> SynthesizedModel:
        """Connect to Postgres and build a graph from INFORMATION_SCHEMA."""
        import asyncpg

        uri = connection_uri.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(uri)
        try:
            tables = [
                r["table_name"]
                for r in await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=$1 AND table_type='BASE TABLE' "
                    "ORDER BY table_name",
                    schema_name,
                )
            ]
            columns = [
                {
                    "table": r["table_name"],
                    "column": r["column_name"],
                    "data_type": r["data_type"],
                    "ordinal": r["ordinal_position"],
                }
                for r in await conn.fetch(
                    "SELECT table_name, column_name, data_type, ordinal_position "
                    "FROM information_schema.columns WHERE table_schema=$1 "
                    "ORDER BY table_name, ordinal_position",
                    schema_name,
                )
            ]
            primary_keys = {
                (r["table_name"], r["column_name"])
                for r in await conn.fetch(
                    "SELECT tc.table_name, kcu.column_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name=kcu.constraint_name "
                    "  AND tc.table_schema=kcu.table_schema "
                    "WHERE tc.constraint_type='PRIMARY KEY' "
                    "  AND tc.table_schema=$1",
                    schema_name,
                )
            }
            foreign_keys = [
                {
                    "from_table": r["from_table"],
                    "from_column": r["from_column"],
                    "to_table": r["to_table"],
                    "to_column": r["to_column"],
                }
                for r in await conn.fetch(
                    "SELECT kcu.table_name AS from_table, "
                    "       kcu.column_name AS from_column, "
                    "       ccu.table_name AS to_table, "
                    "       ccu.column_name AS to_column "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name=kcu.constraint_name "
                    "  AND tc.table_schema=kcu.table_schema "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON tc.constraint_name=ccu.constraint_name "
                    "  AND tc.table_schema=ccu.table_schema "
                    "WHERE tc.constraint_type='FOREIGN KEY' "
                    "  AND tc.table_schema=$1",
                    schema_name,
                )
            ]
        finally:
            await conn.close()

        return IntrospectionService.build_graph(
            tables, columns, primary_keys, foreign_keys
        )
