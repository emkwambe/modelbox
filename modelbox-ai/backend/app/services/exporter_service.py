"""Artifact exporter service.

Transpiles an internal :class:`SynthesizedModel` into production-ready
artifacts (FR-4, Blueprint §7):

* multi-dialect SQL DDL via SQLGlot (PostgreSQL, Snowflake, Databricks,
  BigQuery, DuckDB, …),
* dbt staging models + ``schema.yml`` with column tests,
* Cube.js semantic-layer data models with dimensions, measures, and joins.

Pure/stateless — no database or LLM dependencies — so it is trivially testable
and safe to run in air-gapped deployments.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import sqlglot
import yaml

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    RelationshipSchema,
    SynthesizedModel,
)

if TYPE_CHECKING:
    from app.services.seed_generator import SeedResult

# Map friendly dialect names to SQLGlot dialect identifiers.
_SQLGLOT_DIALECTS: dict[str, str] = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "bigquery": "bigquery",
    "duckdb": "duckdb",
    "redshift": "redshift",
    "clickhouse": "clickhouse",
}


class ExporterError(ValueError):
    """Raised for unsupported dialects or malformed export input."""


class ExporterService:
    """Generates SQL / dbt / Cube.js artifacts from a synthesized model."""

    def __init__(self, source_dialect: str = "snowflake") -> None:
        # Column data types in synthesized models default to Snowflake-style
        # (e.g. NUMBER(18,2), TIMESTAMP_NTZ); parse them as such before writing.
        self._source_dialect = _SQLGLOT_DIALECTS.get(
            source_dialect.lower(), "snowflake"
        )

    # ---------------------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------------------
    def export(
        self,
        model: SynthesizedModel,
        export_format: str,
        dialect: str = "snowflake",
    ) -> dict[str, str]:
        """Dispatch to the requested exporter, returning a file-map artifact."""
        fmt = export_format.lower()
        if fmt == "ddl":
            return {f"model_{dialect}.sql": self.generate_ddl(model, dialect)}
        if fmt == "dbt":
            return self.generate_dbt_project(model)
        if fmt == "cube":
            return self.generate_cube_schema(model)
        raise ExporterError(f"Unsupported export format: {export_format}")

    # ---------------------------------------------------------------------
    # 1. Multi-dialect SQL DDL
    # ---------------------------------------------------------------------
    def generate_ddl(self, model: SynthesizedModel, dialect: str) -> str:
        """Transpile the model's entities to ``CREATE TABLE`` DDL in ``dialect``."""
        target = _SQLGLOT_DIALECTS.get(dialect.lower())
        if target is None:
            raise ExporterError(f"Unsupported target dialect: {dialect}")

        # Separate statements with semicolons so SQLGlot parses each CREATE
        # TABLE individually (otherwise it falls back to opaque passthrough).
        script = ";\n".join(
            self._entity_create_table(entity, model.relationships)
            for entity in model.entities
        )
        statements = sqlglot.transpile(
            script,
            read=self._source_dialect,
            write=target,
            pretty=True,
        )
        return ";\n\n".join(statements) + ";\n"

    def _entity_create_table(
        self, entity: EntitySchema, relationships: list[RelationshipSchema]
    ) -> str:
        """Build a single ANSI ``CREATE TABLE`` string for an entity."""
        lines: list[str] = [
            f"    {col.name} {col.data_type}" for col in entity.columns
        ]

        pk_cols = [c.name for c in entity.columns if c.is_primary_key]
        if pk_cols:
            lines.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

        for rel in relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)
            if from_entity == entity.entity_name and from_col and to_col:
                lines.append(
                    f"    FOREIGN KEY ({from_col}) "
                    f"REFERENCES {to_entity} ({to_col})"
                )

        body = ",\n".join(lines)
        return f"CREATE TABLE {entity.entity_name} (\n{body}\n)"

    # ---------------------------------------------------------------------
    # 2. dbt staging models + schema.yml
    # ---------------------------------------------------------------------
    def generate_dbt_project(
        self, model: SynthesizedModel, source_name: str = "raw"
    ) -> dict[str, str]:
        """Return a map of dbt file paths -> file contents."""
        files: dict[str, str] = {}

        for entity in model.entities:
            path = f"models/staging/stg_{entity.entity_name}.sql"
            files[path] = self._dbt_staging_sql(entity, source_name)

        files["models/staging/schema.yml"] = self._dbt_schema_yml(model)
        return files

    def _dbt_staging_sql(self, entity: EntitySchema, source_name: str) -> str:
        casts = ",\n".join(
            f"    cast({col.name} as {col.data_type}) as {col.name}"
            for col in entity.columns
        )
        return (
            "with source as (\n"
            f"    select * from {{{{ source('{source_name}', "
            f"'{entity.entity_name}') }}}}\n"
            "),\n\n"
            "renamed as (\n"
            "    select\n"
            f"{casts}\n"
            "    from source\n"
            ")\n\n"
            "select * from renamed\n"
        )

    def _dbt_schema_yml(self, model: SynthesizedModel) -> str:
        # Map entity -> its primary-key column for relationship tests.
        pk_by_entity: dict[str, str] = {}
        for entity in model.entities:
            pk = next((c.name for c in entity.columns if c.is_primary_key), None)
            if pk:
                pk_by_entity[entity.entity_name] = pk

        # Map (entity, column) -> referenced "stg_<parent>" for FK relationship tests.
        fk_refs: dict[tuple[str, str], tuple[str, str]] = {}
        for rel in model.relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)
            if from_col and to_col:
                fk_refs[(from_entity, from_col)] = (to_entity, to_col)

        models: list[dict[str, object]] = []
        for entity in model.entities:
            columns: list[dict[str, object]] = []
            for col in entity.columns:
                col_doc: dict[str, object] = {"name": col.name}
                if col.description:
                    col_doc["description"] = col.description

                tests: list[object] = []
                if col.is_primary_key:
                    tests.extend(["unique", "not_null"])
                ref = fk_refs.get((entity.entity_name, col.name))
                if ref:
                    parent_entity, parent_col = ref
                    tests.append(
                        {
                            "relationships": {
                                "to": f"ref('stg_{parent_entity}')",
                                "field": parent_col,
                            }
                        }
                    )
                if tests:
                    col_doc["tests"] = tests
                columns.append(col_doc)

            model_doc: dict[str, object] = {
                "name": f"stg_{entity.entity_name}",
                "columns": columns,
            }
            if entity.description:
                model_doc["description"] = entity.description
            models.append(model_doc)

        return yaml.safe_dump(
            {"version": 2, "models": models}, sort_keys=False, default_flow_style=False
        )

    # ---------------------------------------------------------------------
    # 3b. Synthetic seed data (FR-2.4)
    # ---------------------------------------------------------------------
    def generate_synthetic_seed(
        self,
        model: SynthesizedModel,
        row_count: int = 50,
        seed_format: str = "sql_insert",
        dialect: str = "postgres",
    ) -> "SeedResult":
        """Generate FK-consistent mock rows as SQL INSERTs or a CSV bundle.

        Delegates to :class:`SyntheticSeedGenerator`; returns the file-map plus
        the topological generation order used (parents before children).
        """
        from app.services.seed_generator import SyntheticSeedGenerator

        return SyntheticSeedGenerator(dialect=dialect).generate(
            model, row_count, seed_format
        )

    # ---------------------------------------------------------------------
    # 4. Cube.js semantic layer
    # ---------------------------------------------------------------------
    def generate_cube_schema(self, model: SynthesizedModel) -> dict[str, str]:
        """Return a map of Cube.js file paths -> file contents."""
        files: dict[str, str] = {}
        for entity in model.entities:
            cube_name = self._to_pascal_case(entity.entity_name)
            files[f"schema/{cube_name}.js"] = self._cube_file(entity, model)
        return files

    def _cube_file(self, entity: EntitySchema, model: SynthesizedModel) -> str:
        cube_name = self._to_pascal_case(entity.entity_name)

        dimensions: list[str] = []
        for col in entity.columns:
            props = [
                f"      sql: `{col.name}`",
                f"      type: `{self._cube_type(col)}`",
            ]
            if col.is_primary_key:
                props.append("      primaryKey: true")
            dimensions.append(
                f"    {self._to_camel_case(col.name)}: {{\n"
                + ",\n".join(props)
                + "\n    }"
            )

        measures = [
            "    count: {\n      type: `count`\n    }",
        ]
        for col in entity.columns:
            if col.is_metric or self._is_numeric(col):
                agg = (col.aggregation or "sum").lower()
                measures.append(
                    f"    total{self._to_pascal_case(col.name)}: {{\n"
                    f"      sql: `{col.name}`,\n"
                    f"      type: `{agg}`\n    }}"
                )

        joins: list[str] = []
        for rel in model.relationships:
            from_entity, _ = self._split_ref(rel.from_ref)
            to_entity, _ = self._split_ref(rel.to_ref)
            if from_entity == entity.entity_name and to_entity != entity.entity_name:
                target = self._to_pascal_case(to_entity)
                from_col = self._split_ref(rel.from_ref)[1]
                to_col = self._split_ref(rel.to_ref)[1]
                joins.append(
                    f"    {target}: {{\n"
                    f"      sql: `${{CUBE}}.{from_col} = ${{{target}}}.{to_col}`,\n"
                    f"      relationship: `belongsTo`\n    }}"
                )

        sections = [
            f"  sql_table: `{entity.entity_name}`,\n",
            "  joins: {\n" + ",\n".join(joins) + "\n  },\n" if joins else "  joins: {},\n",
            "  dimensions: {\n" + ",\n".join(dimensions) + "\n  },\n",
            "  measures: {\n" + ",\n".join(measures) + "\n  }",
        ]
        return f"cube(`{cube_name}`, {{\n" + "".join(sections) + "\n});\n"

    # ---------------------------------------------------------------------
    # 5. Data contracts (Phase 3, FR-2.3)
    # ---------------------------------------------------------------------
    def export_data_contract(
        self,
        model: SynthesizedModel,
        contract_format: str,
        dataset_name: str = "modelbox_dataset",
    ) -> dict[str, str]:
        """Emit a governance data contract in the requested format."""
        fmt = contract_format.lower()
        if fmt in ("opendatacontract", "odcs"):
            return {"datacontract.yaml": self._odcs_contract(model, dataset_name)}
        if fmt == "avro":
            return {
                f"{entity.entity_name}.avsc": self._avro_schema(entity, dataset_name)
                for entity in model.entities
            }
        if fmt in ("protobuf", "proto", "proto3"):
            return {f"{dataset_name}.proto": self._protobuf_schema(model, dataset_name)}
        raise ExporterError(f"Unsupported contract format: {contract_format}")

    def _odcs_contract(self, model: SynthesizedModel, dataset_name: str) -> str:
        """Open Data Contract Standard (v0.9.x) YAML."""
        schema: list[dict[str, object]] = []
        for entity in model.entities:
            properties: list[dict[str, object]] = []
            for col in entity.columns:
                prop: dict[str, object] = {
                    "name": col.name,
                    "logicalType": self._logical_type(col.data_type),
                    "physicalType": col.data_type,
                    "required": col.is_primary_key,
                    "primaryKey": col.is_primary_key,
                }
                if col.description:
                    prop["description"] = col.description
                if col.is_pii:
                    prop["classification"] = "PII"
                properties.append(prop)
            table_doc: dict[str, object] = {
                "name": entity.entity_name,
                "physicalType": "table",
                "properties": properties,
            }
            if entity.description:
                table_doc["description"] = entity.description
            schema.append(table_doc)

        contract = {
            "apiVersion": "v0.9.3",
            "kind": "DataContract",
            "id": dataset_name,
            "info": {
                "title": dataset_name,
                "version": "1.0.0",
                "owner": "modelbox",
            },
            "schema": schema,
        }
        return yaml.safe_dump(contract, sort_keys=False, default_flow_style=False)

    def _avro_schema(self, entity: EntitySchema, namespace: str) -> str:
        """Apache Avro record schema (JSON) for one entity."""
        fields: list[dict[str, object]] = []
        for col in entity.columns:
            avro_type = self._avro_type(col.data_type)
            # Non-key columns are nullable via a ["null", T] union defaulting null.
            if not col.is_primary_key:
                field: dict[str, object] = {
                    "name": col.name,
                    "type": ["null", avro_type],
                    "default": None,
                }
            else:
                field = {"name": col.name, "type": avro_type}
            if col.description:
                field["doc"] = col.description
            fields.append(field)

        record = {
            "type": "record",
            "name": self._to_pascal_case(entity.entity_name),
            "namespace": namespace,
            "fields": fields,
        }
        return json.dumps(record, indent=2)

    def _protobuf_schema(self, model: SynthesizedModel, package: str) -> str:
        """Protobuf proto3 message definitions for the whole model."""
        lines = ['syntax = "proto3";', "", f"package {package};", ""]
        for entity in model.entities:
            lines.append(f"message {self._to_pascal_case(entity.entity_name)} {{")
            for tag, col in enumerate(entity.columns, start=1):
                lines.append(f"  {self._proto_type(col.data_type)} {col.name} = {tag};")
            lines.append("}")
            lines.append("")
        return "\n".join(lines)

    # ---------------------------------------------------------------------
    # 6. Semantic layers (Phase 3, FR-2.3)
    # ---------------------------------------------------------------------
    def export_semantic_layer(
        self, model: SynthesizedModel, engine: str
    ) -> dict[str, str]:
        """Emit a semantic-layer definition for the requested BI engine."""
        eng = engine.lower()
        if eng == "cube":
            return self.generate_cube_schema(model)
        if eng == "lookml":
            return {
                f"{entity.entity_name}.view.lkml": self._lookml_view(entity)
                for entity in model.entities
            }
        if eng == "metricflow":
            return {"semantic_models.yml": self._metricflow(model)}
        raise ExporterError(f"Unsupported semantic engine: {engine}")

    def _lookml_view(self, entity: EntitySchema) -> str:
        lines = [f"view: {entity.entity_name} {{", f"  sql_table_name: {entity.entity_name} ;;", ""]
        for col in entity.columns:
            if self._is_temporal(col.data_type):
                lines.append(f"  dimension_group: {col.name} {{")
                lines.append("    type: time")
                lines.append("    timeframes: [raw, date, week, month, quarter, year]")
                lines.append(f"    sql: ${{TABLE}}.{col.name} ;;")
                lines.append("  }")
            else:
                lines.append(f"  dimension: {col.name} {{")
                if col.is_primary_key:
                    lines.append("    primary_key: yes")
                lines.append(f"    type: {self._lookml_type(col.data_type)}")
                lines.append(f"    sql: ${{TABLE}}.{col.name} ;;")
                lines.append("  }")
            lines.append("")

        for col in entity.columns:
            if self._is_numeric(col) and not col.is_primary_key:
                agg = (col.aggregation or "sum").lower()
                lines.append(f"  measure: total_{col.name} {{")
                lines.append(f"    type: {agg}")
                lines.append(f"    sql: ${{TABLE}}.{col.name} ;;")
                lines.append("  }")
                lines.append("")

        lines.append("  measure: count {")
        lines.append("    type: count")
        lines.append("  }")
        lines.append("}")
        return "\n".join(lines)

    def _metricflow(self, model: SynthesizedModel) -> str:
        # Map (entity, column) -> parent for foreign-key entity declarations.
        fk_refs: dict[tuple[str, str], str] = {}
        for rel in model.relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, _ = self._split_ref(rel.to_ref)
            if from_col:
                fk_refs[(from_entity, from_col)] = to_entity

        semantic_models: list[dict[str, object]] = []
        metrics: list[dict[str, object]] = []
        for entity in model.entities:
            entities_block: list[dict[str, object]] = []
            dimensions: list[dict[str, object]] = []
            measures: list[dict[str, object]] = []

            for col in entity.columns:
                if col.is_primary_key:
                    entities_block.append(
                        {"name": col.name, "type": "primary", "expr": col.name}
                    )
                elif (entity.entity_name, col.name) in fk_refs:
                    entities_block.append(
                        {"name": col.name, "type": "foreign", "expr": col.name}
                    )
                elif self._is_temporal(col.data_type):
                    dimensions.append(
                        {
                            "name": col.name,
                            "type": "time",
                            "type_params": {"time_granularity": "day"},
                            "expr": col.name,
                        }
                    )
                elif self._is_numeric(col):
                    measures.append(
                        {
                            "name": f"total_{col.name}",
                            "agg": (col.aggregation or "sum").lower(),
                            "expr": col.name,
                        }
                    )
                else:
                    dimensions.append(
                        {"name": col.name, "type": "categorical", "expr": col.name}
                    )

            count_measure = f"{entity.entity_name}_count"
            measures.append({"name": count_measure, "agg": "count", "expr": "1"})
            metrics.append(
                {
                    "name": count_measure,
                    "type": "simple",
                    "type_params": {"measure": count_measure},
                }
            )

            model_doc: dict[str, object] = {
                "name": entity.entity_name,
                "model": f"ref('{entity.entity_name}')",
                "entities": entities_block,
            }
            if dimensions:
                model_doc["dimensions"] = dimensions
            model_doc["measures"] = measures
            semantic_models.append(model_doc)

        return yaml.safe_dump(
            {"semantic_models": semantic_models, "metrics": metrics},
            sort_keys=False,
            default_flow_style=False,
        )

    # ---------------------------------------------------------------------
    # Type mapping helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _logical_type(data_type: str) -> str:
        t = data_type.upper()
        if any(tok in t for tok in ("INT", "SERIAL", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "NUMBER")):
            return "number"
        if "BOOL" in t:
            return "boolean"
        if any(tok in t for tok in ("TIMESTAMP", "DATE", "TIME")):
            return "date"
        return "string"

    @staticmethod
    def _is_temporal(data_type: str) -> bool:
        t = data_type.upper()
        return any(tok in t for tok in ("TIMESTAMP", "DATETIME", "DATE", "TIME"))

    def _avro_type(self, data_type: str) -> object:
        t = data_type.upper()
        if "BOOL" in t:
            return "boolean"
        if any(tok in t for tok in ("BIGINT", "BIGSERIAL")):
            return "long"
        if "TIMESTAMP" in t or "DATETIME" in t:
            return {"type": "long", "logicalType": "timestamp-micros"}
        if "DATE" in t:
            return {"type": "int", "logicalType": "date"}
        if any(tok in t for tok in ("NUMERIC", "DECIMAL", "NUMBER")):
            precision, scale = self._parse_precision_scale(data_type)
            return {
                "type": "bytes",
                "logicalType": "decimal",
                "precision": precision,
                "scale": scale,
            }
        if any(tok in t for tok in ("FLOAT", "DOUBLE", "REAL")):
            return "double"
        if any(tok in t for tok in ("INT", "SERIAL")):
            return "int"
        return "string"

    @staticmethod
    def _proto_type(data_type: str) -> str:
        t = data_type.upper()
        if "BOOL" in t:
            return "bool"
        if any(tok in t for tok in ("BIGINT", "BIGSERIAL")):
            return "int64"
        if any(tok in t for tok in ("FLOAT", "DOUBLE", "REAL", "NUMERIC", "DECIMAL", "NUMBER")):
            return "double"
        if any(tok in t for tok in ("INT", "SERIAL")):
            return "int32"
        return "string"

    def _lookml_type(self, data_type: str) -> str:
        t = data_type.upper()
        if "BOOL" in t:
            return "yesno"
        if any(
            tok in t
            for tok in ("INT", "SERIAL", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "NUMBER")
        ):
            return "number"
        return "string"

    @staticmethod
    def _parse_precision_scale(data_type: str) -> tuple[int, int]:
        match = re.search(r"\((\d+)\s*,\s*(\d+)\)", data_type)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 38, 9

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _split_ref(ref: str) -> tuple[str, str]:
        parts = ref.split(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")

    @staticmethod
    def _is_numeric(col: ColumnSchema) -> bool:
        upper = col.data_type.upper()
        return any(
            tok in upper
            for tok in ("INT", "NUMBER", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL")
        )

    def _cube_type(self, col: ColumnSchema) -> str:
        upper = col.data_type.upper()
        if any(tok in upper for tok in ("DATE", "TIME", "TIMESTAMP")):
            return "time"
        if self._is_numeric(col):
            return "number"
        return "string"

    @staticmethod
    def _to_pascal_case(name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_") if part)

    @staticmethod
    def _to_camel_case(name: str) -> str:
        parts = [p for p in name.split("_") if p]
        if not parts:
            return name
        return parts[0] + "".join(p.capitalize() for p in parts[1:])
