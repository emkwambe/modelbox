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
    _is_temporal_type,
)

if TYPE_CHECKING:
    from app.services.seed_generator import SeedResult

# Conventional value sets for common categorical columns. Used to scaffold dbt
# accepted_values tests only where the values are well-known — we never fabricate
# a values list we can't stand behind.
_CATEGORICAL_VALUES: dict[str, list[str]] = {
    "status": ["ACTIVE", "INACTIVE", "PENDING"],
    "tier": ["BRONZE", "SILVER", "GOLD", "PLATINUM"],
    "priority": ["LOW", "MEDIUM", "HIGH"],
    "severity": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
}

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
                accepted = self._accepted_values(col)
                if accepted:
                    tests.append({"accepted_values": {"values": accepted}})
                tests.extend(self._dbt_quality_tests(col))
                if tests:
                    col_doc["tests"] = tests
                columns.append(col_doc)

            model_doc: dict[str, object] = {
                "name": f"stg_{entity.entity_name}",
                "columns": columns,
            }
            if entity.description:
                model_doc["description"] = entity.description
            meta = self._governance_meta(entity)
            if meta:
                model_doc["meta"] = meta
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
                quality = self._odcs_quality(col)
                if quality:
                    prop["quality"] = quality
                properties.append(prop)
            table_doc: dict[str, object] = {
                "name": entity.entity_name,
                "physicalType": "table",
                "properties": properties,
            }
            if entity.description:
                table_doc["description"] = entity.description
            tier = self._tier_value(entity)
            if tier:
                table_doc["tier"] = tier
            if entity.freshness_sla:
                table_doc["slaProperties"] = [
                    {"property": "freshness", "value": entity.freshness_sla}
                ]
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
            # Avro namespaces must be valid dotted identifiers (no spaces).
            "namespace": self._safe_identifier(namespace),
            "fields": fields,
        }
        return json.dumps(record, indent=2)

    def _protobuf_schema(self, model: SynthesizedModel, package: str) -> str:
        """Protobuf proto3 message definitions for the whole model."""
        # proto3 package names must be valid identifiers (no spaces/punctuation).
        safe_package = self._safe_identifier(package)
        lines = ['syntax = "proto3";', "", f"package {safe_package};", ""]
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
            if _is_temporal_type(col.data_type):
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
        """Emit a dbt semantic layer that ``dbt parse`` accepts (B1).

        Seven defects were fixed together here because none of them is visible
        on its own: ``dbt parse`` fails on the first, so nothing downstream can
        be observed until all of the blocking ones are correct.

        The load-bearing rules:

        * A measure needs a time axis. An entity with no ``agg_time_column``
          therefore declares **no measures** and is dimension-only, rather than
          being given an invented one. Six of the fifteen reference entities
          have no temporal column at all.
        * A foreign entity is named after the **parent's primary entity**, with
          ``expr`` carrying the local column. MetricFlow resolves joins by
          entity name, so naming it after the local FK column only worked when
          that name coincidentally equalled the parent's key.
        * A name colliding with a reserved granularity keyword is suffixed —
          and ``defaults.agg_time_dimension`` must then reference the
          **renamed** dimension. Renaming without that would fix one defect and
          silently reintroduce another.
        """
        # (child entity, child column) -> parent entity, for foreign entities.
        fk_parent: dict[tuple[str, str], str] = {}
        for rel in model.relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, _ = self._split_ref(rel.to_ref)
            if from_col:
                fk_parent[(from_entity, from_col)] = to_entity

        # Each entity's primary-entity name, which is its primary-key column.
        # A foreign entity must reuse the parent's, or the join does not exist.
        primary_entity_name: dict[str, str] = {}
        for entity in model.entities:
            pk = next((c.name for c in entity.columns if c.is_primary_key), None)
            if pk is not None:
                primary_entity_name[entity.entity_name] = self._safe_semantic_name(pk)

        semantic_models: list[dict[str, object]] = []
        metrics: list[dict[str, object]] = []

        for entity in model.entities:
            entities_block: list[dict[str, object]] = []
            dimensions: list[dict[str, object]] = []
            measures: list[dict[str, object]] = []

            # A measure without a time axis is unemittable, so the entity's
            # declared aggregation time dimension decides whether it has any.
            agg_time_dimension: str | None = None
            if entity.agg_time_column:
                agg_time_dimension = self._safe_semantic_name(entity.agg_time_column)

            for col in entity.columns:
                safe_name = self._safe_semantic_name(col.name)
                parent = fk_parent.get((entity.entity_name, col.name))

                if col.is_primary_key:
                    entities_block.append(
                        {"name": safe_name, "type": "primary", "expr": col.name}
                    )
                elif parent is not None:
                    entities_block.append(
                        {
                            # The parent's primary entity, not the local column.
                            "name": primary_entity_name.get(parent, safe_name),
                            "type": "foreign",
                            "expr": col.name,
                        }
                    )
                elif _is_temporal_type(col.data_type):
                    dimensions.append(
                        {
                            "name": safe_name,
                            "type": "time",
                            "type_params": {"time_granularity": "day"},
                            "expr": col.name,
                        }
                    )
                elif col.is_metric or self._is_numeric(col):
                    if agg_time_dimension is None:
                        # No time axis: express it as a dimension rather than
                        # dropping the column from the semantic model entirely.
                        dimensions.append(
                            {"name": safe_name, "type": "categorical", "expr": col.name}
                        )
                        continue
                    measure_name = f"total_{col.name}"
                    measures.append(
                        {
                            "name": measure_name,
                            "agg": self._metricflow_agg(col.aggregation),
                            "expr": col.name,
                        }
                    )
                else:
                    dimensions.append(
                        {"name": safe_name, "type": "categorical", "expr": col.name}
                    )

            if agg_time_dimension is not None:
                count_measure = f"{entity.entity_name}_count"
                measures.append({"name": count_measure, "agg": "count", "expr": "1"})

            for measure in measures:
                name = str(measure["name"])
                metrics.append(
                    {
                        "name": name,
                        # dbt requires a label on every metric.
                        "label": name.replace("_", " ").strip().title(),
                        "type": "simple",
                        "type_params": {"measure": name},
                    }
                )

            model_doc: dict[str, object] = {
                "name": entity.entity_name,
                # The dbt exporter names its models stg_<entity>; referencing
                # the bare entity pointed at a node that does not exist.
                "model": f"ref('stg_{entity.entity_name}')",
                "entities": entities_block,
            }
            if entity.entity_name not in primary_entity_name and dimensions:
                # A satellite or bridge with no single-column key still needs a
                # primary entity once it declares dimensions.
                model_doc["primary_entity"] = entity.entity_name
            if measures:
                model_doc["defaults"] = {"agg_time_dimension": agg_time_dimension}
            if dimensions:
                model_doc["dimensions"] = dimensions
            if measures:
                model_doc["measures"] = measures
            semantic_models.append(model_doc)

        document: dict[str, object] = {"semantic_models": semantic_models}
        if metrics:
            document["metrics"] = metrics
        return yaml.safe_dump(document, sort_keys=False, default_flow_style=False)

    # MetricFlow's AggregationType. Mapped explicitly rather than lower-cased
    # through, because `avg` — the obvious spelling, and what the canvas offers
    # — is not a member and made dbt exit with a traceback rather than a parse
    # error.
    _METRICFLOW_AGGREGATIONS: dict[str, str] = {
        "sum": "sum",
        "min": "min",
        "max": "max",
        "count": "count",
        "count_distinct": "count_distinct",
        "distinct_count": "count_distinct",
        "avg": "average",
        "average": "average",
        "mean": "average",
        "median": "median",
        "percentile": "percentile",
        "sum_boolean": "sum_boolean",
    }

    @classmethod
    def _metricflow_agg(cls, aggregation: str | None) -> str:
        """Translate a declared aggregation into MetricFlow's vocabulary.

        Raises rather than passing an unknown value through: a refused export
        names the problem, whereas an unmapped aggregation surfaces as a
        traceback from inside ``dbt parse`` pointing at a generated file.
        """
        if not aggregation:
            return "sum"
        key = aggregation.strip().lower()
        try:
            return cls._METRICFLOW_AGGREGATIONS[key]
        except KeyError:
            raise ExporterError(
                f"Aggregation {aggregation!r} has no MetricFlow equivalent. "
                f"Supported: "
                f"{', '.join(sorted(set(cls._METRICFLOW_AGGREGATIONS.values())))}."
            ) from None

    # MetricFlow rejects any name equal to a time-granularity keyword.
    _RESERVED_GRANULARITIES = frozenset(
        {
            "nanosecond", "microsecond", "millisecond", "second", "minute",
            "hour", "day", "week", "month", "quarter", "year",
        }
    )

    @classmethod
    def _safe_semantic_name(cls, name: str) -> str:
        """Suffix a name that collides with a reserved granularity keyword.

        ``expr`` carries the real column, so the identifier is free to differ.
        Every producer of a semantic name goes through here, including the one
        that builds ``defaults.agg_time_dimension`` — the two must agree or the
        default points at a dimension that was renamed out from under it.
        """
        if name.lower() in cls._RESERVED_GRANULARITIES:
            return f"{name}_dim"
        return name

    # ---------------------------------------------------------------------
    # 7. Data dictionary & business glossary (Phase 3, Pick 2)
    # ---------------------------------------------------------------------
    def export_data_dictionary(
        self,
        model: SynthesizedModel,
        dictionary_format: str,
        dataset_name: str = "modelbox_dataset",
    ) -> dict[str, str]:
        """Emit a human/machine-readable data dictionary + business glossary."""
        fmt = dictionary_format.lower()
        if fmt in ("markdown", "md"):
            return {"data_dictionary.md": self._dict_markdown(model, dataset_name)}
        if fmt == "html":
            return {"data_dictionary.html": self._dict_html(model, dataset_name)}
        if fmt == "json":
            return {"data_dictionary.json": self._dict_json(model, dataset_name)}
        raise ExporterError(f"Unsupported dictionary format: {dictionary_format}")

    def _fk_targets(self, model: SynthesizedModel) -> dict[tuple[str, str], str]:
        targets: dict[tuple[str, str], str] = {}
        for rel in model.relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            if from_col:
                targets[(from_entity, from_col)] = rel.to_ref
        return targets

    @staticmethod
    def _key_label(col: ColumnSchema, fk_ref: str | None) -> str:
        if col.is_primary_key:
            return "PK"
        if col.is_foreign_key or fk_ref:
            return f"FK → {fk_ref}" if fk_ref else "FK"
        return ""

    @staticmethod
    def _pii_label(col: ColumnSchema) -> str:
        if col.is_pii:
            return col.pii_type or "PII"
        return ""

    @staticmethod
    def _md_cell(value: str | None) -> str:
        """Escape a value for a Markdown table cell."""
        if not value:
            return ""
        return value.replace("|", "\\|").replace("\n", " ").strip()

    def _dict_markdown(self, model: SynthesizedModel, dataset_name: str) -> str:
        targets = self._fk_targets(model)
        lines: list[str] = [
            f"# Data Dictionary — {dataset_name}",
            "",
            "_Generated by ModelBox AI._",
            "",
            f"- **Paradigm:** {self._paradigm_value(model)}",
            f"- **Entities:** {len(model.entities)}",
            "",
            "## Entities",
            "",
        ]
        for entity in model.entities:
            lines.append(f"### {entity.entity_name} ({self._entity_type_value(entity)})")
            if entity.description:
                lines.append("")
                lines.append(self._md_cell(entity.description))
            if entity.grain:
                lines.append("")
                lines.append(f"**Grain:** {self._md_cell(entity.grain)}")
            lines.append("")
            lines.append("| Column | Type | Key | PII | Description |")
            lines.append("|---|---|---|---|---|")
            for col in entity.columns:
                fk_ref = targets.get((entity.entity_name, col.name))
                lines.append(
                    f"| {self._md_cell(col.name)} "
                    f"| {self._md_cell(col.data_type)} "
                    f"| {self._md_cell(self._key_label(col, fk_ref))} "
                    f"| {self._md_cell(self._pii_label(col))} "
                    f"| {self._md_cell(col.description)} |"
                )
            lines.append("")

        if model.relationships:
            lines.append("## Relationships")
            lines.append("")
            lines.append("| From | To | Cardinality |")
            lines.append("|---|---|---|")
            for rel in model.relationships:
                card = rel.cardinality
                card_value = card.value if hasattr(card, "value") else str(card)
                lines.append(
                    f"| {self._md_cell(rel.from_ref)} "
                    f"| {self._md_cell(rel.to_ref)} | {card_value} |"
                )
            lines.append("")

        # Business glossary — documented terms only (undocumented items are a
        # governance gap surfaced elsewhere, not filler here).
        glossary: list[tuple[str, str]] = []
        for entity in model.entities:
            if entity.description:
                glossary.append((entity.entity_name, entity.description))
            for col in entity.columns:
                if col.description:
                    glossary.append((f"{entity.entity_name}.{col.name}", col.description))
        if glossary:
            lines.append("## Business Glossary")
            lines.append("")
            lines.append("| Term | Definition |")
            lines.append("|---|---|")
            for term, definition in glossary:
                lines.append(f"| {self._md_cell(term)} | {self._md_cell(definition)} |")
            lines.append("")

        return "\n".join(lines)

    def _dict_html(self, model: SynthesizedModel, dataset_name: str) -> str:
        targets = self._fk_targets(model)

        def esc(value: str | None) -> str:
            if not value:
                return ""
            return (
                value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        parts: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="en"><head><meta charset="utf-8">',
            f"<title>Data Dictionary — {esc(dataset_name)}</title>",
            "<style>"
            "body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#0f172a}"
            "h1{margin-bottom:0}h2{margin-top:2rem;border-bottom:1px solid #e2e8f0}"
            "table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
            "th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left;font-size:14px}"
            "th{background:#f8fafc}.pii{color:#b91c1c;font-weight:600}"
            ".muted{color:#64748b}code{background:#f1f5f9;padding:1px 4px;border-radius:4px}"
            "</style></head><body>",
            f"<h1>Data Dictionary — {esc(dataset_name)}</h1>",
            f'<p class="muted">Generated by ModelBox AI · paradigm '
            f"{esc(self._paradigm_value(model))} · {len(model.entities)} entities</p>",
        ]
        for entity in model.entities:
            parts.append(
                f"<h2>{esc(entity.entity_name)} "
                f'<span class="muted">({esc(self._entity_type_value(entity))})</span></h2>'
            )
            if entity.description:
                parts.append(f"<p>{esc(entity.description)}</p>")
            if entity.grain:
                parts.append(f"<p><strong>Grain:</strong> {esc(entity.grain)}</p>")
            parts.append(
                "<table><thead><tr><th>Column</th><th>Type</th><th>Key</th>"
                "<th>PII</th><th>Description</th></tr></thead><tbody>"
            )
            for col in entity.columns:
                fk_ref = targets.get((entity.entity_name, col.name))
                pii = self._pii_label(col)
                pii_cell = f'<span class="pii">{esc(pii)}</span>' if pii else ""
                parts.append(
                    f"<tr><td><code>{esc(col.name)}</code></td>"
                    f"<td>{esc(col.data_type)}</td>"
                    f"<td>{esc(self._key_label(col, fk_ref))}</td>"
                    f"<td>{pii_cell}</td>"
                    f"<td>{esc(col.description)}</td></tr>"
                )
            parts.append("</tbody></table>")

        if model.relationships:
            parts.append("<h2>Relationships</h2>")
            parts.append(
                "<table><thead><tr><th>From</th><th>To</th>"
                "<th>Cardinality</th></tr></thead><tbody>"
            )
            for rel in model.relationships:
                card = rel.cardinality
                card_value = card.value if hasattr(card, "value") else str(card)
                parts.append(
                    f"<tr><td><code>{esc(rel.from_ref)}</code></td>"
                    f"<td><code>{esc(rel.to_ref)}</code></td>"
                    f"<td>{esc(card_value)}</td></tr>"
                )
            parts.append("</tbody></table>")

        parts.append("</body></html>")
        return "\n".join(parts)

    def _dict_json(self, model: SynthesizedModel, dataset_name: str) -> str:
        targets = self._fk_targets(model)
        entities: list[dict[str, object]] = []
        for entity in model.entities:
            columns: list[dict[str, object]] = []
            for col in entity.columns:
                fk_ref = targets.get((entity.entity_name, col.name))
                columns.append(
                    {
                        "name": col.name,
                        "data_type": col.data_type,
                        "primary_key": col.is_primary_key,
                        "foreign_key": col.is_foreign_key or fk_ref is not None,
                        "references": fk_ref,
                        "pii": col.is_pii,
                        "pii_type": col.pii_type.value
                        if hasattr(col.pii_type, "value")
                        else col.pii_type,
                        "description": col.description,
                    }
                )
            entities.append(
                {
                    "name": entity.entity_name,
                    "type": self._entity_type_value(entity),
                    "description": entity.description,
                    "grain": entity.grain,
                    "columns": columns,
                }
            )
        doc = {
            "dataset": dataset_name,
            "generated_by": "ModelBox AI",
            "paradigm": self._paradigm_value(model),
            "entities": entities,
            "relationships": [
                {
                    "from": rel.from_ref,
                    "to": rel.to_ref,
                    "cardinality": rel.cardinality.value
                    if hasattr(rel.cardinality, "value")
                    else str(rel.cardinality),
                }
                for rel in model.relationships
            ],
        }
        return json.dumps(doc, indent=2)

    @staticmethod
    def _paradigm_value(model: SynthesizedModel) -> str:
        p = model.paradigm
        return p.value if hasattr(p, "value") else str(p)

    @staticmethod
    def _entity_type_value(entity: EntitySchema) -> str:
        t = entity.entity_type
        return t.value if hasattr(t, "value") else str(t)

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

    @staticmethod
    def _safe_identifier(name: str, fallback: str = "modelbox") -> str:
        """Coerce an arbitrary name into a valid proto/Avro identifier.

        Titles like ``"Untitled Model"`` contain spaces that are illegal as
        Protobuf package names or Avro namespaces; collapse to snake_case.
        """
        ident = re.sub(r"\W+", "_", name).strip("_").lower()
        if not ident:
            return fallback
        if ident[0].isdigit():
            return f"{fallback}_{ident}"
        return ident

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

    @staticmethod
    def _tier_value(entity: EntitySchema) -> str | None:
        tier = entity.tier
        if tier is None:
            return None
        return tier.value if hasattr(tier, "value") else str(tier)

    @classmethod
    def _governance_meta(cls, entity: EntitySchema) -> dict[str, str]:
        """dbt meta block carrying declared governance metadata."""
        meta: dict[str, str] = {}
        tier = cls._tier_value(entity)
        if tier:
            meta["tier"] = tier
        if entity.freshness_sla:
            meta["freshness_sla"] = entity.freshness_sla
        return meta

    @staticmethod
    def _is_string_type(col: ColumnSchema) -> bool:
        upper = col.data_type.upper()
        return any(tok in upper for tok in ("CHAR", "TEXT", "STRING", "VARCHAR"))

    @staticmethod
    def _dbt_quality_tests(col: ColumnSchema) -> list[object]:
        """Declared quality rules -> dbt_expectations column tests (Sprint U3).

        Numeric bounds become ``expect_column_values_to_be_between`` and a regex
        becomes ``expect_column_values_to_match_regex`` — the de-facto dbt way to
        express range/pattern assertions.
        """
        tests: list[object] = []
        if col.min_value is not None or col.max_value is not None:
            between: dict[str, object] = {}
            if col.min_value is not None:
                between["min_value"] = col.min_value
            if col.max_value is not None:
                between["max_value"] = col.max_value
            tests.append(
                {"dbt_expectations.expect_column_values_to_be_between": between}
            )
        if col.regex_pattern and col.regex_pattern.strip():
            tests.append(
                {
                    "dbt_expectations.expect_column_values_to_match_regex": {
                        "regex": col.regex_pattern
                    }
                }
            )
        return tests

    @staticmethod
    def _odcs_quality(col: ColumnSchema) -> list[dict[str, object]]:
        """Declared quality rules -> ODCS column ``quality`` assertions (U3)."""
        quality: list[dict[str, object]] = []
        if col.min_value is not None or col.max_value is not None:
            rule: dict[str, object] = {"rule": "range"}
            if col.min_value is not None:
                rule["mustBeGreaterThanOrEqualTo"] = col.min_value
            if col.max_value is not None:
                rule["mustBeLessThanOrEqualTo"] = col.max_value
            quality.append(rule)
        if col.regex_pattern and col.regex_pattern.strip():
            quality.append({"rule": "regex", "pattern": col.regex_pattern})
        return quality

    @classmethod
    def _accepted_values(cls, col: ColumnSchema) -> list[str] | None:
        """Conventional accepted values for a categorical string column, or None.

        Matches by column name (exact or ``*_<name>``) against a curated set of
        well-known enums so the emitted dbt test asserts real values, not guesses.
        """
        if not cls._is_string_type(col):
            return None
        name = col.name.lower()
        for key, values in _CATEGORICAL_VALUES.items():
            if name == key or name.endswith(f"_{key}"):
                return values
        return None

    def _cube_type(self, col: ColumnSchema) -> str:
        if _is_temporal_type(col.data_type):
            return "time"
        if "BOOL" in col.data_type.upper():
            # Cube has a boolean dimension type. Omitting this branch typed
            # every BOOLEAN column as `string` (M3), while _logical_type and
            # _lookml_type both handled booleans — the disagreement between
            # three private copies of the same predicate that the shared
            # _is_temporal_type now prevents.
            return "boolean"
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
