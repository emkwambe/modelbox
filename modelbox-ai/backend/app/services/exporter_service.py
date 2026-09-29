"""Artifact exporter service.

Transpiles an internal :class:`SynthesizedModel` into production-ready
artifacts (FR-4, Blueprint §7):

* multi-dialect SQL DDL via SQLGlot (PostgreSQL, Snowflake, Databricks,
  BigQuery, DuckDB, …),
* dbt staging models + ``schema.yml`` with column tests,
* Cube.js semantic-layer data models with dimensions, measures, and joins.

Pure/stateless — no database or LLM dependencies — so it is trivially testable
and safe to run in air-gapped deployments.

Declared IR outranks heuristics
-------------------------------
A product-wide precedence rule, stated here because it was violated
independently in two subsystems and the second violation was found only after
the first was fixed.

Several code paths carry name-driven guesses — a column called ``status`` draws
from a conventional ACTIVE/INACTIVE/PENDING vocabulary, a column called ``email``
gets an email-shaped value. Those guesses are useful **only where the model has
said nothing**. Where the IR declares a constraint — ``check_expression``,
``min_value``/``max_value``, ``regex_pattern``, a declared ``VARCHAR(n)``,
``is_unique``, ``is_nullable`` — the declaration wins, always, with no exceptions
per field.

The failure this prevents is not an oversight, which is why it needs a rule
rather than a fix per site. In both violations the code had read the model and
disagreed with it: the seed generator emitted ``INACTIVE`` for a column
declaring ``CHECK (status IN ('PENDING','DONE'))`` (H1), and the dbt exporter
emitted an ``accepted_values`` test asserting the same wrong vocabulary (H11).
A guess that overrides a contract is worse than no guess at all, because it
looks deliberate.

Two corollaries, both discovered the hard way:

* **Declared constraints can conflict with each other**, and satisfying one
  must be done knowing the other. A length clamp applied to distinct values can
  make them identical, violating a declared UNIQUE.
* **Referential integrity outranks a declared UNIQUE.** A foreign key must
  repeat whatever the parent holds; a model declaring both is stating a 1:1,
  and the FK constraint is the one that cannot be bent.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

import yaml

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
    _is_temporal_type,
)
from app.services.ddl_export import DdlExport, DdlExportError, build_ddl

if TYPE_CHECKING:
    from app.services.seed_generator import SeedResult

# Conventional value sets for common categorical columns.
#
# **Not used for any contract term** (S5-1). This once fed the dbt
# `accepted_values` test, which meant a column named `status` acquired three
# permitted values the model never declared. A name is evidence about intent; it
# is not a declaration, and only a declaration may become a term the customer's
# data is tested against.
#
# Retained for seed *scaffolding*, where a plausible sample value is the whole
# point and asserts nothing. Kept deliberately rather than deleted, because the
# distinction — guess freely for sample data, never for a contract — is the rule
# worth keeping visible.
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
    # Source dialects only: an imported model's types, defaults and CHECK
    # expressions are written in the dialect it was imported from.
    "oracle": "oracle",
    "tsql": "tsql",
}
_DDL_TARGETS = frozenset({"postgres", "snowflake", "databricks", "bigquery", "duckdb", "redshift", "clickhouse"})


# Open Data Contract Standard version this emitter targets. Bitol, verified via
# context7 on 2026-08-11. Bump only alongside a re-read of the spec — the
# previous value claimed v0.9.3 while the body used v3 vocabulary, so the
# artifact conformed to neither.
_ODCS_API_VERSION = "v3.1.0"


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
        """``CREATE TABLE`` and ``COMMENT ON`` DDL for the model in ``dialect``.

        Export gaps, if any, head the file as comments; see
        :meth:`generate_ddl_export` for them as data.
        """
        return self.generate_ddl_export(model, dialect).sql

    def generate_ddl_export(self, model: SynthesizedModel, dialect: str) -> DdlExport:
        """The DDL and its export gaps (``app.services.ddl_export``)."""
        target = _SQLGLOT_DIALECTS.get(dialect.lower())
        if target is None or target not in _DDL_TARGETS:
            raise ExporterError(f"Unsupported target dialect: {dialect}")
        try:
            return build_ddl(model, target, self._source_dialect)
        except DdlExportError as exc:
            raise ExporterError(str(exc)) from exc

    def _require_valid_fragments(self, entity: EntitySchema) -> None:
        """Refuse an entity whose data types or defaults are not exactly SQL.

        They are interpolated into the script below, so one that does not parse
        as a single type or expression is refused with its lint code and never
        emitted verbatim (`app.services.sql_fragments`, Sprint 7 Step 2.4).
        """
        from app.services.sql_fragments import column_problems

        for column in entity.columns:
            problems = column_problems(column.data_type, column.default_value, self._source_dialect)
            if problems:
                code, reason = problems[0]
                raise ExporterError(
                    f"{code}: column '{entity.entity_name}.{column.name}': {reason}."
                )

    # ---------------------------------------------------------------------
    # 2. dbt staging models + schema.yml
    # ---------------------------------------------------------------------
    def generate_dbt_project(
        self, model: SynthesizedModel, source_name: str = "raw"
    ) -> dict[str, str]:
        """Return a map of dbt file paths -> file contents.

        The project must parse standalone (B14). It previously emitted staging
        models referencing ``{{ source(...) }}`` without ever declaring those
        sources, so ``dbt parse`` failed on the first model with "depends on a
        source named 'raw.x' which was not found" — every consumer had to
        hand-write the sources file before the artifact was usable.
        """
        files: dict[str, str] = {}

        for entity in model.entities:
            path = f"models/staging/stg_{entity.entity_name}.sql"
            files[path] = self._dbt_staging_sql(entity, source_name)

        files["models/staging/_sources.yml"] = self._dbt_sources_yml(
            model, source_name
        )
        files["models/staging/schema.yml"] = self._dbt_schema_yml(model)

        # Only emitted when something actually depends on it — a packages.yml
        # naming an unused package is its own kind of noise.
        packages = self._dbt_packages_yml(model)
        if packages is not None:
            files["packages.yml"] = packages
        gaps = self.dbt_export_gaps(model)
        if gaps:
            files["EXPORT_GAPS.md"] = (
                "# Export gaps\n\nKeys this project does not test, and why.\n\n"
                + "".join(f"- {gap}\n" for gap in gaps))
        return files

    def _dbt_sources_yml(self, model: SynthesizedModel, source_name: str) -> str:
        """Declare the raw sources the staging models select from (B14)."""
        return yaml.safe_dump(
            {
                "version": 2,
                "sources": [
                    {
                        "name": source_name,
                        "description": (
                            "Raw tables the staging models read from. Point "
                            "`schema` at wherever these land in your warehouse."
                        ),
                        "schema": source_name,
                        "tables": [
                            {"name": entity.entity_name}
                            for entity in model.entities
                        ],
                    }
                ],
            },
            sort_keys=False,
            default_flow_style=False,
        )

    def _dbt_packages_yml(self, model: SynthesizedModel) -> str | None:
        """Declare dbt_expectations when a quality rule makes us depend on it.

        Emitting the tests without the dependency produced a project that could
        not resolve its own tests (M7).

        **A version range is a list of strings** — ``[">=0.10.0", "<0.11.0"]``.
        This emitted each bound as a single-key mapping instead, which dbt
        rejects outright: not a warning, the project will not load at all
        (H12). It survived a full release because no gold graph declares a
        quality rule, so no project the harness ever handed to dbt carried a
        packages.yml, and the test that covered this asserted only that a file
        with the right name existed.

        **The package is `metaplane/dbt_expectations`.** `calogica/*` is
        redirected on dbt Hub and resolving it raises PackageRedirectDeprecation
        — twice, because its own transitive `dbt_date` is redirected too, which
        is inside the upstream package and not ours to fix. Verified against
        dbt 1.11.12 on 2026-09-01: `metaplane/dbt_expectations` 0.10.10 pulls
        `godatadriven/dbt_date` 0.21.0 and resolves with zero deprecations,
        which is what keeps B12 reachable for a project with quality rules.
        `scripts/refresh_dbt_packages.py` is the gate that enforces it — the
        deprecations fire against the registry, so no offline check can see them.
        """
        needs_expectations = any(
            self._dbt_quality_tests(col)
            for entity in model.entities
            for col in entity.columns
        ) or any(self._compound_uniques(entity) for entity in model.entities)
        if not needs_expectations:
            return None
        return yaml.safe_dump(
            {
                "packages": [
                    {
                        "package": "metaplane/dbt_expectations",
                        "version": [">=0.10.0", "<0.11.0"],
                    }
                ]
            },
            sort_keys=False,
            default_flow_style=False,
        )

    def _dbt_staging_sql(self, entity: EntitySchema, source_name: str) -> str:
        self._require_valid_fragments(entity)
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

    @staticmethod
    def _compound_uniques(entity: EntitySchema) -> list[list[str]]:
        """Column sets that must be unique together: a composite key or a multi-column UNIQUE."""
        sets = [entity.primary_key] if len(entity.primary_key) > 1 else []
        return sets + [u.columns for u in entity.unique_constraints if len(u.columns) > 1]

    @staticmethod
    def dbt_export_gaps(model: SynthesizedModel) -> list[str]:
        """Keys the dbt project cannot test: dbt's relationships test is one column."""
        gaps = []
        for rel in model.relationships:
            label = f"{rel.from_ref}({', '.join(rel.from_columns)}) -> {rel.to_ref}({', '.join(rel.to_columns)})"
            if not rel.resolved:
                gaps.append(f"{label}: unresolved, its columns are not chosen; no relationships test")
            elif len(rel.from_columns) > 1:
                gaps.append(f"{label}: composite foreign key; dbt's relationships test takes one column")
        return gaps

    def _dbt_schema_yml(self, model: SynthesizedModel) -> str:
        # Map (entity, column) -> referenced "stg_<parent>" for FK relationship
        # tests: one-column relationships only (see dbt_export_gaps).
        fk_refs: dict[tuple[str, str], tuple[str, str]] = {}
        for rel in model.relationships:
            if rel.resolved and len(rel.from_columns) == 1:
                fk_refs[(rel.from_ref, rel.from_columns[0])] = (rel.to_ref, rel.to_columns[0])

        models: list[dict[str, object]] = []
        for entity in model.entities:
            single_key = entity.primary_key if len(entity.primary_key) == 1 else []
            single_unique = {u.columns[0] for u in entity.unique_constraints if len(u.columns) == 1}
            columns: list[dict[str, object]] = []
            for col in entity.columns:
                col_doc: dict[str, object] = {"name": col.name}
                if col.description:
                    col_doc["description"] = col.description

                # A generic test's arguments nest under `arguments:` (M11).
                # Passing them at the top level is deprecated in dbt 1.11 and
                # warned on every parse.
                tests: list[object] = []
                if col.name in single_key:
                    tests.extend(["unique", "not_null"])
                elif col.is_primary_key:
                    # A member of a composite key is not unique alone; the
                    # combination is tested at the model level below.
                    tests.append("not_null")
                elif col.name in single_unique:
                    tests.append("unique")
                ref = fk_refs.get((entity.entity_name, col.name))
                if ref:
                    parent_entity, parent_col = ref
                    tests.append(
                        {
                            "relationships": {
                                "arguments": {
                                    "to": f"ref('stg_{parent_entity}')",
                                    "field": parent_col,
                                }
                            }
                        }
                    )
                accepted = self._accepted_values(col)
                if accepted:
                    tests.append(
                        {"accepted_values": {"arguments": {"values": accepted}}}
                    )
                tests.extend(self._dbt_quality_tests(col))
                if tests:
                    col_doc["data_tests"] = tests
                columns.append(col_doc)

            model_doc: dict[str, object] = {
                "name": f"stg_{entity.entity_name}",
                "columns": columns,
            }
            compound = self._compound_uniques(entity)
            if compound:
                model_doc["data_tests"] = [
                    {"dbt_expectations.expect_compound_columns_to_be_unique": {
                        "arguments": {"column_list": columns_set}}}
                    for columns_set in compound]
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
    ) -> SeedResult:
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
            # A key is an identifier that happens to be stored as a number.
            # SUM(customer_sk) and SUM(order_line_sk) are arithmetic on
            # identifiers — numerically valid, semantically meaningless, and
            # offered to every BI user as though they meant something (M3).
            # Both halves matter: excluding only foreign keys would still sum
            # a surrogate primary key that nothing references.
            if col.is_primary_key or col.is_foreign_key:
                continue
            if col.is_metric or self._is_numeric(col):
                agg = (col.aggregation or "sum").lower()
                measures.append(
                    f"    total{self._to_pascal_case(col.name)}: {{\n"
                    f"      sql: `{col.name}`,\n"
                    f"      type: `{agg}`\n    }}"
                )

        joins: list[str] = []
        for rel in model.relationships:
            # An unresolved relationship names no columns, so it has no join
            # condition to state; a composite one joins on every pair.
            if rel.from_ref == entity.entity_name and rel.to_ref != entity.entity_name and rel.resolved:
                target = self._to_pascal_case(rel.to_ref)
                condition = " AND ".join(f"${{CUBE}}.{f} = ${{{target}}}.{t}" for f, t in rel.pairs)
                joins.append(
                    f"    {target}: {{\n"
                    f"      sql: `{condition}`,\n"
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
            # The filename is sanitised as well as the package name. dataset_name
            # is the model title, so an untitled model produced
            # "Untitled Model.proto" — a filename protoc will not import.
            return {
                f"{self._safe_identifier(dataset_name)}.proto":
                    self._protobuf_schema(model, dataset_name)
            }
        raise ExporterError(f"Unsupported contract format: {contract_format}")

    def _odcs_contract(self, model: SynthesizedModel, dataset_name: str) -> str:
        """Open Data Contract Standard v3.1.0 (Bitol).

        Spec: https://github.com/bitol-io/open-data-contract-standard
        Verified via context7 on 2026-08-11 — this emitter had previously been
        a hybrid of two standards, so the shape is asserted against the
        published one rather than remembered.

        * Required at the top level: ``apiVersion``, ``kind``, ``id``,
          ``version``, ``status``. ``name`` is optional; ``dataProduct`` is
          deprecated since v3.1.0.
        * There is **no** ``info:`` block. That belongs to the Data Contract
          Specification (datacontract.com), a different standard, and emitting
          it made the artifact conform to neither.
        * A foreign key at property level is ``relationships: [{to: ...}]``
          with ``from`` implicit. ``type: foreignKey`` is the *schema*-level
          construct and requires explicit ``from`` and ``to`` — correction
          C7-a, after C3 named this wrongly.
        """
        schema: list[dict[str, object]] = []
        # A composite foreign key is not a set of one-column relationships, so
        # its columns carry none; it is stated whole as a custom property.
        composite = {(r.from_ref, c) for r in model.relationships if len(r.from_columns) > 1 for c in r.from_columns}
        for entity in model.entities:
            properties: list[dict[str, object]] = []
            for col in entity.columns:
                prop: dict[str, object] = {
                    "name": col.name,
                    "logicalType": self._logical_type(col.data_type),
                    "physicalType": col.data_type,
                    # Derived from declared nullability, not restated from the
                    # key flag. Under the old rule every non-key column was
                    # declared optional — including Data Vault load_dts and
                    # record_source, which are structurally mandatory.
                    "required": not col.is_nullable,
                    "primaryKey": col.is_primary_key,
                }
                if col.is_primary_key and len(entity.primary_key) > 1:
                    prop["primaryKeyPosition"] = entity.primary_key.index(col.name) + 1
                if col.is_unique:
                    prop["unique"] = True
                if col.description:
                    prop["description"] = col.description
                if col.is_pii:
                    prop["classification"] = "PII"
                if col.references and (entity.entity_name, col.name) not in composite:
                    # Shorthand notation, <object>.<property>, which is exactly
                    # the shape ColumnSchema.references already stores.
                    prop["relationships"] = [{"to": col.references}]
                options = self._odcs_logical_type_options(col)
                if options:
                    prop["logicalTypeOptions"] = options
                quality = self._odcs_quality(col)
                if quality:
                    prop["quality"] = quality
                properties.append(prop)

            table_doc: dict[str, object] = {
                "name": entity.entity_name,
                "logicalType": "object",
                "physicalType": "table",
                "properties": properties,
            }
            if entity.description:
                table_doc["description"] = entity.description
            custom: list[dict[str, object]] = []
            tier = self._tier_value(entity)
            if tier:
                # `tier` is not an ODCS schema key; carrying it as a custom
                # property keeps the information without inventing vocabulary.
                custom.append({"property": "tier", "value": tier})
            if entity.grain:
                custom.append({"property": "grain", "value": entity.grain})
            keys = [f"({', '.join(r.from_columns)}) -> {r.to_ref}({', '.join(r.to_columns)})"
                    for r in model.relationships if r.from_ref == entity.entity_name and len(r.from_columns) > 1]
            if keys:
                custom.append({"property": "compositeForeignKeys", "value": keys})
            multi_unique = [u.columns for u in entity.unique_constraints if len(u.columns) > 1]
            if multi_unique:
                custom.append({"property": "uniqueColumnSets", "value": multi_unique})
            if custom:
                table_doc["customProperties"] = custom
            if entity.freshness_sla:
                table_doc["slaProperties"] = [
                    {"property": "freshness", "value": entity.freshness_sla}
                ]
            schema.append(table_doc)

        contract = {
            "apiVersion": _ODCS_API_VERSION,
            "kind": "DataContract",
            "id": self._safe_identifier(dataset_name),
            "name": dataset_name,
            "version": "1.0.0",
            "status": "draft",
            "schema": schema,
        }
        return yaml.safe_dump(contract, sort_keys=False, default_flow_style=False)

    def _avro_schema(self, entity: EntitySchema, namespace: str) -> str:
        """Apache Avro record schema (JSON) for one entity."""
        fields: list[dict[str, object]] = []
        for col in entity.columns:
            avro_type = self._avro_type(col.data_type)
            # Nullability comes from `is_nullable`, never from `is_primary_key`.
            # This branched on the key flag until Sprint 5, which is the same
            # fact on all six gold graphs — every key is non-nullable and every
            # non-key column is nullable — so the defect was invisible to every
            # test that existed (correction C7). A column declared NOT NULL in
            # DDL and `required` in ODCS was emitted as a nullable union here,
            # and the three artifacts disagreed about the same IR field.
            # Found by the cross-artifact gate on its first run.
            if col.is_nullable:
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
        """Protobuf proto3 message definitions for the whole model.

        **Field tags come from ``ColumnSchema.stable_id``, never from position.**
        A tag is a wire-format contract: a deployed consumer decodes field 3 as
        whatever field 3 meant when it was generated. Numbering by list position
        meant inserting a column silently renumbered every later field, so an
        existing consumer misparsed every one of them — finding H6, and the
        reason ``stable_id`` exists at all.

        The identity is allocated once at first persist and never reused, and
        the allocator already skips protoc's reserved 19000-19999, so nothing
        needs special-casing here.

        A model that has never been persisted has no identities yet. It falls
        back to position, which is honest: an unsaved draft has no wire contract
        to keep. Anything exported through the API has been persisted, so the
        guarantee holds wherever it can meaningfully be claimed.
        """
        # proto3 package names must be valid identifiers (no spaces/punctuation).
        safe_package = self._safe_identifier(package)
        lines = ['syntax = "proto3";', "", f"package {safe_package};", ""]
        for entity in model.entities:
            lines.append(f"message {self._to_pascal_case(entity.entity_name)} {{")
            for position, col in enumerate(entity.columns, start=1):
                tag = col.stable_id if col.stable_id is not None else position
                lines.append(
                    f"  {self._proto_type(col.data_type)} {col.name} = {tag};"
                )
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
        # One-column foreign keys only: a MetricFlow entity is one expression.
        fk_parent: dict[tuple[str, str], str] = {}
        for rel in model.relationships:
            if len(rel.from_columns) == 1:
                fk_parent[(rel.from_ref, rel.from_columns[0])] = rel.to_ref

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
    _METRICFLOW_AGGREGATIONS: ClassVar[dict[str, str]] = {
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
            for i, from_col in enumerate(rel.from_columns):
                to_col = rel.to_columns[i] if i < len(rel.to_columns) else None
                targets[(rel.from_ref, from_col)] = f"{rel.to_ref}.{to_col}" if to_col else rel.to_ref
        return targets

    @staticmethod
    def _side(entity: str, columns: list[str]) -> str:
        """One end of a relationship as a reader sees it: entity.column, or entity(a, b)."""
        if len(columns) == 1:
            return f"{entity}.{columns[0]}"
        return f"{entity}({', '.join(columns)})" if columns else entity

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
                    f"| {self._md_cell(self._side(rel.from_ref, rel.from_columns))} "
                    f"| {self._md_cell(self._side(rel.to_ref, rel.to_columns))} | {card_value} |"
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
            (
                "<style>"
                "body{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#0f172a}"
                "h1{margin-bottom:0}h2{margin-top:2rem;border-bottom:1px solid #e2e8f0}"
                "table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
                "th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left;font-size:14px}"
                "th{background:#f8fafc}.pii{color:#b91c1c;font-weight:600}"
                ".muted{color:#64748b}code{background:#f1f5f9;padding:1px 4px;border-radius:4px}"
                "</style></head><body>"
            ),
            f"<h1>Data Dictionary — {esc(dataset_name)}</h1>",
            (
                f'<p class="muted">Generated by ModelBox AI · paradigm '
                f"{esc(self._paradigm_value(model))} · {len(model.entities)} entities</p>"
            ),
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
                    f"<tr><td><code>{esc(self._side(rel.from_ref, rel.from_columns))}</code></td>"
                    f"<td><code>{esc(self._side(rel.to_ref, rel.to_columns))}</code></td>"
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
                        if isinstance(col.pii_type, Enum)
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
                    "from_columns": rel.from_columns,
                    "to": rel.to_ref,
                    "to_columns": rel.to_columns,
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
        if any(tok in t for tok in ("NUMERIC", "DECIMAL", "NUMBER")):
            # Exact numerics carry as `string`, not `double`. A ledger balance
            # declared NUMERIC(18,2) is exact by definition, and proto3 has no
            # fixed-point scalar — mapping it to a binary float silently makes
            # money approximate. That is a correctness defect, not a style one:
            # Avro already emits a decimal logical type with precision and
            # scale from the same column, so the two contracts disagreed about
            # the same value. A decimal string round-trips exactly and is what
            # google.type.Decimal and most financial schemas do.
            return "string"
        if any(tok in t for tok in ("FLOAT", "DOUBLE", "REAL")):
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

        Arguments nest under ``arguments:`` (M14). Sprint 3's M11 made that
        change for ``accepted_values`` and stopped there, so half of one defect
        was fixed and the other half raised
        MissingArgumentsPropertyInGenericTestDeprecation for another release.
        Nothing caught it because no project containing these tests was ever
        parsed — the deprecation gate ran on gold graphs, and no gold graph
        declares a quality rule.
        """
        tests: list[object] = []
        if col.min_value is not None or col.max_value is not None:
            between: dict[str, object] = {}
            if col.min_value is not None:
                between["min_value"] = col.min_value
            if col.max_value is not None:
                between["max_value"] = col.max_value
            tests.append(
                {
                    "dbt_expectations.expect_column_values_to_be_between": {
                        "arguments": between
                    }
                }
            )
        if col.regex_pattern and col.regex_pattern.strip():
            tests.append(
                {
                    "dbt_expectations.expect_column_values_to_match_regex": {
                        "arguments": {"regex": col.regex_pattern}
                    }
                }
            )
        return tests

    @staticmethod
    def _odcs_quality(col: ColumnSchema) -> list[dict[str, object]]:
        """Declared rules -> ODCS v3.1.0 property ``quality`` entries (H10).

        The old output was `{"rule": "range", "mustBeGreaterThanOrEqualTo": …}`
        and `{"rule": "regex", "pattern": …}`. **`rule` is not an ODCS key**,
        and neither shape appears anywhere in the standard.

        A v3.1.0 entry is `{id, type, metric, mustBe*, arguments, unit,
        description}`, where `metric` names a library metric that returns a
        number and `mustBe*` compares it. The one that fits a declared domain
        constraint is `invalidValues`: it counts rows failing the constraint, so
        the assertion is `mustBe: 0`.

        **A numeric range is deliberately NOT emitted here.** Verified against
        Bitol's `data-quality.md` and `schema.md` via context7 on 2026-08-11:
        the documented `invalidValues` arguments are `validValues` (a list) and
        `pattern`. There is no documented argument for a numeric bound, and
        inventing one — `validMinimum`, say — would produce a document that
        validates as ODCS and means nothing to any engine reading it. A range
        belongs in `logicalTypeOptions.minimum/maximum`, which is where
        `_odcs_logical_type_options` now puts it. That is a relocation, not a
        loss: the constraint still reaches the contract, by the name the
        standard gives it.
        """
        quality: list[dict[str, object]] = []
        if col.regex_pattern and col.regex_pattern.strip():
            quality.append(
                {
                    "id": f"{col.name}_pattern",
                    "metric": "invalidValues",
                    "mustBe": 0,
                    "unit": "rows",
                    "arguments": {"pattern": col.regex_pattern},
                    "description": (
                        f"Every value of {col.name} must match "
                        f"{col.regex_pattern}."
                    ),
                }
            )
        allowed = ExporterService._check_enum_literals(col.check_expression)
        if allowed:
            quality.append(
                {
                    "id": f"{col.name}_valid_values",
                    "metric": "invalidValues",
                    "mustBe": 0,
                    "unit": "rows",
                    "arguments": {"validValues": allowed},
                    "description": (
                        f"{col.name} accepts only {', '.join(allowed)}."
                    ),
                }
            )
        return quality

    @staticmethod
    def _declared_length(data_type: str) -> int | None:
        match = re.search(r"(?:VAR)?CHAR\s*\(\s*(\d+)\s*\)", data_type, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _odcs_logical_type_options(col: ColumnSchema) -> dict[str, object]:
        """Declared domain constraints -> ODCS ``logicalTypeOptions``.

        Where the standard puts a *bound*, as opposed to a *check*. Per
        `schema.md`: integer and number support `minimum`, `maximum` and
        `multipleOf`; string supports `format`, `minLength`, `maxLength` and
        `pattern`.

        The distinction is real rather than stylistic. `logicalTypeOptions`
        declares what values the column may hold; `quality` declares a measured
        assertion with a threshold and a unit. A declared range is the former,
        which is why moving it here rather than forcing it into an
        `invalidValues` argument that does not exist is the correct fix for
        that half of H10.
        """
        options: dict[str, object] = {}
        logical = ExporterService._logical_type(col.data_type)
        if logical in ("integer", "number"):
            if col.min_value is not None:
                options["minimum"] = col.min_value
            if col.max_value is not None:
                options["maximum"] = col.max_value
        if logical == "string":
            if col.regex_pattern and col.regex_pattern.strip():
                options["pattern"] = col.regex_pattern
            length = ExporterService._declared_length(col.data_type)
            if length is not None:
                options["maxLength"] = length
        return options

    @classmethod
    def _accepted_values(cls, col: ColumnSchema) -> list[str] | None:
        """Accepted values for a categorical string column, or None.

        **Declared IR outranks heuristics** — the product-wide precedence rule
        (see the module docstring). A declared ``CHECK (col IN (...))`` is the
        model stating its own vocabulary, and it wins outright.

        H11. This used to consult only ``_CATEGORICAL_VALUES``, so a column
        named ``status`` got ACTIVE/INACTIVE/PENDING even when its model
        declared ``CHECK (status IN ('PENDING','DONE'))``. The docstring above
        this one claimed the emitter "never fabricates a values list we can't
        stand behind", which is precisely what it did the moment the model
        declared one — and the guess did not merely fill a gap, it overrode the
        contract.

        The consequence was cross-artifact and therefore invisible to every
        gate: the exported dbt test demanded one vocabulary while the seed
        generator, reading the same model correctly after H1, produced another.
        Each artifact was valid against its own consumer. Together they could
        not both be right, and only ``dbt build`` could see it.
        """
        if not cls._is_string_type(col):
            return None

        # S5-1. **Declared or nothing.** The name-driven fallback that used to
        # stand here returned ACTIVE/INACTIVE/PENDING for any column called
        # `status`, whether or not the model declared a vocabulary — so a model
        # that said nothing acquired three permitted values it never had, and
        # they shipped as a dbt test run against the customer's own data. A user
        # whose statuses are PENDING and DONE got a red build on correct data.
        #
        # H11 fixed the half where a guess *overrode* a declaration. This is the
        # other half: a guess *filling a silence*. The module docstring above
        # says guesses are useful "only where the model has said nothing" — true
        # for scaffolding seed data, which is sample data, and false here,
        # because an `accepted_values` test is a contract term. A guess exported
        # as a contract is worse than saying nothing, which is exactly what the
        # synthesis prompt tells the model and what the emitter must also obey.
        return cls._check_enum_literals(col.check_expression)

    @staticmethod
    def _check_enum_literals(expression: str | None) -> list[str] | None:
        """Allowed literals from a simple ``col IN ('a', 'b')`` CHECK.

        Deliberately as narrow as the seed generator's `_check_enum`, and for
        the same reason: an emitter cannot evaluate an arbitrary SQL predicate,
        and pretending to would be untested handling that fails silently on the
        first expression it cannot parse. Anything that is not an enumeration
        falls through to the heuristics, which is the correct behaviour — the
        model has not stated a vocabulary, so there is nothing to outrank.
        """
        if not expression or " IN " not in expression.upper():
            return None
        literals = re.findall(r"'([^']*)'", expression)
        return literals or None

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
