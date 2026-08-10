"""Database introspection service (FR-2.1).

Reads an existing database's ``INFORMATION_SCHEMA`` and constructs a
``SynthesizedModel`` graph ready for GraphEngine linting and paradigm
transformation. The metadata->graph mapping is a pure function
(:meth:`build_graph`) so it is fully unit-testable without a live database.
"""

from __future__ import annotations

import urllib.parse
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

# Snowflake INFORMATION_SCHEMA.COLUMNS.data_type -> normalized type.
_SNOWFLAKE_TYPE_MAP: dict[str, str] = {
    "number": "DECIMAL",
    "decimal": "DECIMAL",
    "numeric": "NUMERIC",
    "int": "INT",
    "integer": "INT",
    "bigint": "BIGINT",
    "smallint": "SMALLINT",
    "tinyint": "SMALLINT",
    "byteint": "SMALLINT",
    "float": "DOUBLE",
    "float4": "DOUBLE",
    "float8": "DOUBLE",
    "double": "DOUBLE",
    "double precision": "DOUBLE",
    "real": "REAL",
    "varchar": "VARCHAR",
    "char": "CHAR",
    "character": "CHAR",
    "string": "VARCHAR",
    "text": "VARCHAR",
    "binary": "BINARY",
    "varbinary": "BINARY",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "time": "TIME",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "timestamp_ntz": "TIMESTAMP",
    "timestamp_ltz": "TIMESTAMPTZ",
    "timestamp_tz": "TIMESTAMPTZ",
    "variant": "VARIANT",
    "object": "OBJECT",
    "array": "ARRAY",
    "geography": "GEOGRAPHY",
}


class IntrospectionDriverError(RuntimeError):
    """Raised when the driver for a database engine is not installed."""


def _map_type(data_type: str, type_map: dict[str, str] | None = None) -> str:
    return (type_map or _PG_TYPE_MAP).get(data_type.lower(), data_type.upper())


class IntrospectionService:
    """Introspects physical schemas into ModelBox graphs."""

    @staticmethod
    def build_graph(
        tables: list[str],
        columns: list[dict[str, Any]],
        primary_keys: set[tuple[str, str]],
        foreign_keys: list[dict[str, str]],
        type_map: dict[str, str] | None = None,
    ) -> SynthesizedModel:
        """Pure mapping of DB metadata -> a 3NF ``SynthesizedModel``.

        Entity type is inferred from FK topology: >=2 outgoing FKs -> FACT;
        referenced with <=1 outgoing -> DIMENSION; otherwise TABLE. ``type_map``
        selects the engine's data-type normalization (defaults to PostgreSQL).
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
                    data_type=_map_type(col["data_type"], type_map),
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

    # -----------------------------------------------------------------------
    # Snowflake (Pick 3)
    # -----------------------------------------------------------------------
    @staticmethod
    def _parse_snowflake_uri(uri: str) -> dict[str, str]:
        """Parse a snowflake:// URI into snowflake.connector.connect kwargs.

        Pure and testable — no driver required. Form:
        ``snowflake://user:password@account/database[/schema]?warehouse=wh&role=r``
        """
        parts = urllib.parse.urlsplit(uri)
        path = [p for p in parts.path.split("/") if p]
        query = urllib.parse.parse_qs(parts.query)
        params: dict[str, str] = {}
        if parts.username:
            params["user"] = urllib.parse.unquote(parts.username)
        if parts.password:
            params["password"] = urllib.parse.unquote(parts.password)
        if parts.hostname:
            params["account"] = parts.hostname
        if path:
            params["database"] = path[0]
        if len(path) > 1:
            params["schema"] = path[1]
        for key in ("warehouse", "role"):
            if key in query and query[key]:
                params[key] = query[key][0]
        return params

    @staticmethod
    def _snowflake_connect_kwargs(uri: str, schema_name: str) -> dict[str, str]:
        """Final connect() kwargs. The explicit schema_name is authoritative,
        so it replaces any schema parsed from the URI (avoids a duplicate kwarg).
        """
        params = IntrospectionService._parse_snowflake_uri(uri)
        params["schema"] = schema_name
        return params

    @staticmethod
    async def introspect_snowflake(
        connection_uri: str, schema_name: str = "PUBLIC"
    ) -> SynthesizedModel:
        """Introspect a Snowflake schema into a graph.

        The driver is imported lazily so the base appliance stays lean. Tables
        and columns come from INFORMATION_SCHEMA; keys come from SHOW PRIMARY
        KEYS / SHOW IMPORTED KEYS (Snowflake lacks KEY_COLUMN_USAGE). Key
        extraction is defensive — if it fails, a column-only model is still
        returned.
        """
        import asyncio

        try:
            import snowflake.connector as sf  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise IntrospectionDriverError(
                "snowflake-connector-python is not installed on the appliance."
            ) from exc

        params = IntrospectionService._snowflake_connect_kwargs(
            connection_uri, schema_name
        )

        def _lower_keys(row: dict[str, Any]) -> dict[str, Any]:
            return {str(k).lower(): v for k, v in row.items()}

        def _run() -> tuple[
            list[str],
            list[dict[str, Any]],
            set[tuple[str, str]],
            list[dict[str, str]],
        ]:
            conn = sf.connect(**params)
            try:
                cur = conn.cursor(sf.DictCursor)
                tables = [
                    _lower_keys(r)["table_name"]
                    for r in cur.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                        "ORDER BY table_name",
                        (schema_name,),
                    )
                ]
                columns = [
                    {
                        "table": lr["table_name"],
                        "column": lr["column_name"],
                        "data_type": lr["data_type"],
                        "ordinal": lr["ordinal_position"],
                    }
                    for r in cur.execute(
                        "SELECT table_name, column_name, data_type, "
                        "ordinal_position FROM information_schema.columns "
                        "WHERE table_schema = %s "
                        "ORDER BY table_name, ordinal_position",
                        (schema_name,),
                    )
                    for lr in (_lower_keys(r),)
                ]

                # Keys via SHOW commands (best-effort; Snowflake declares but
                # does not enforce constraints).
                primary_keys: set[tuple[str, str]] = set()
                foreign_keys: list[dict[str, str]] = []
                try:
                    for r in cur.execute(f"SHOW PRIMARY KEYS IN SCHEMA {schema_name}"):
                        lr = _lower_keys(r)
                        primary_keys.add((lr["table_name"], lr["column_name"]))
                    for r in cur.execute(f"SHOW IMPORTED KEYS IN SCHEMA {schema_name}"):
                        lr = _lower_keys(r)
                        foreign_keys.append(
                            {
                                "from_table": lr["fk_table_name"],
                                "from_column": lr["fk_column_name"],
                                "to_table": lr["pk_table_name"],
                                "to_column": lr["pk_column_name"],
                            }
                        )
                except Exception:  # noqa: BLE001 - keys are best-effort
                    pass

                return tables, columns, primary_keys, foreign_keys
            finally:
                conn.close()

        tables, columns, primary_keys, foreign_keys = await asyncio.to_thread(_run)
        return IntrospectionService.build_graph(
            tables, columns, primary_keys, foreign_keys, type_map=_SNOWFLAKE_TYPE_MAP
        )
