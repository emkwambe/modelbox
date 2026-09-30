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
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

import yaml

from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
    _is_temporal_type,
    is_integer_type,
    type_family,
)
from app.services.ddl_export import (
    DdlExport,
    DdlExportError,
    build_ddl,
    column_type,
    quote,
)

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
}
# Dialects a model's fragments may be written in: every target, and the two
# import dialects that are not export targets. An imported model's types,
# defaults and CHECK expressions are in the dialect it was imported from.
_SOURCE_DIALECTS: dict[str, str] = {**_SQLGLOT_DIALECTS, "oracle": "oracle", "tsql": "tsql"}


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
        self._source_dialect = _SOURCE_DIALECTS.get(
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
            return self.generate_dbt_project(model, dialect=dialect)
        if fmt == "cube":
            return self._with_notes(self.generate_cube_schema(model), model, "cube")
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

    def generate_ddl_export(self, model: SynthesizedModel, dialect: str,
                            extensions: frozenset[str] = frozenset()) -> DdlExport:
        """The DDL and its export gaps (``app.services.ddl_export``).

        ``extensions`` are the target extensions the caller says the target
        has (``ltree``, ``postgis``); none is ever assumed.
        """
        target = _SQLGLOT_DIALECTS.get(dialect.lower())
        if target is None:
            raise ExporterError(f"Unsupported target dialect: {dialect}")
        try:
            return build_ddl(model, target, self._source_dialect, extensions)
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
        self, model: SynthesizedModel, source_name: str = "raw", dialect: str | None = None
    ) -> dict[str, str]:
        """Return a map of dbt file paths -> file contents.

        The project must parse standalone (B14). It previously emitted staging
        models referencing ``{{ source(...) }}`` without ever declaring those
        sources, so ``dbt parse`` failed on the first model with "depends on a
        source named 'raw.x' which was not found" — every consumer had to
        hand-write the sources file before the artifact was usable.

        ``dialect`` is the warehouse the project runs on. Each staging column is
        cast to its type there, written as the DDL export writes it for that
        dialect, mappings included (Sprint 9 Step 2b): a model imported from
        Oracle cast to ``NUMBER(4, 0)``, which PostgreSQL does not have. Without
        a dialect, types are written in the model's own. Either way a column the
        DDL export does not create (a computed column that is a gap) has no
        staging column and no test.
        """
        # Every fragment is checked before any is translated, so a malformed
        # type is refused with its lint code, never as a translation failure.
        for entity in model.entities:
            self._require_valid_fragments(entity)
        types: dict[tuple[str, str], str | None]
        if dialect is None:
            # The declared text exactly; a computed column has no type to cast to.
            types = {(e.entity_name, c.name): (None if c.data_type == "COMPUTED" else c.data_type)
                     for e in model.entities for c in e.columns}
        else:
            target = _SQLGLOT_DIALECTS.get(dialect.lower())
            if target is None:
                raise ExporterError(f"Unsupported target dialect: {dialect}")
            try:
                types = {(e.entity_name, c.name): column_type(c, e, self._source_dialect, target)
                         for e in model.entities for c in e.columns}
            except DdlExportError as exc:
                raise ExporterError(str(exc)) from exc
        files: dict[str, str] = {}

        for entity in model.entities:
            path = f"models/staging/stg_{entity.entity_name}.sql"
            files[path] = self._dbt_staging_sql(entity, source_name, types)

        files["models/staging/_sources.yml"] = self._dbt_sources_yml(
            model, source_name
        )
        files["models/staging/schema.yml"] = self._dbt_schema_yml(model, types)

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

    def _dbt_staging_sql(self, entity: EntitySchema, source_name: str,
                         types: dict[tuple[str, str], str | None]) -> str:
        self._require_valid_fragments(entity)
        # Named as the DDL export names them: a mixed-case name is quoted, or
        # PostgreSQL folds WorkOrderID to workorderid and finds no column.
        casts = ",\n".join(
            f"    cast({quote(col.name)} as {written}) as {quote(col.name)}"
            for col in entity.columns
            if (written := types[(entity.entity_name, col.name)]) is not None
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

    def _dbt_schema_yml(self, model: SynthesizedModel,
                        types: dict[tuple[str, str], str | None] | None = None) -> str:
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
                if types is not None and types.get((entity.entity_name, col.name)) is None:
                    continue  # not a column of the staging model (see generate_dbt_project)
                col_doc: dict[str, object] = {"name": col.name}
                if quote(col.name) != col.name:
                    # A generic test's column_name is written as given; quote it
                    # as the staging model's column is quoted.
                    col_doc["quote"] = True
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
                                    # The macro writes `field` as given.
                                    "field": quote(parent_col),
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
                        "arguments": {"column_list": [quote(c) for c in columns_set]}}}
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
        Each column is generated for its type in ``dialect``, as the DDL export
        writes it from the model's source dialect.
        """
        from app.services.seed_generator import SyntheticSeedGenerator

        target = _SQLGLOT_DIALECTS.get(dialect.lower(), dialect)
        return SyntheticSeedGenerator(dialect=target, source_dialect=self._source_dialect).generate(
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
            # a surrogate primary key that nothing references. Codes are not
            # summed either (dimension_reason), and the notes say which.
            if col.is_primary_key or col.is_foreign_key or self.dimension_reason(col, entity, model) is not None:
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
            return self._with_notes(self.generate_cube_schema(model), model, eng)
        if eng == "lookml":
            return self._with_notes({
                f"{entity.entity_name}.view.lkml": self._lookml_view(entity, model)
                for entity in model.entities
            }, model, eng)
        if eng == "metricflow":
            document, renamed = self._metricflow_document(model)
            files = {"semantic_models.yml": yaml.safe_dump(document, sort_keys=False, default_flow_style=False)}
            gaps = self.metricflow_export_gaps(model)
            notes = self.semantic_notes(model, eng) + renamed
            header = []
            if gaps:
                # Stated twice: at the head of the YAML, which travels on its
                # own, and as its own file, as the dbt project does.
                header = [f"# Export gaps ({len(gaps)}): keys this semantic model does not state."]
                header += [f"# - {gap}" for gap in gaps]
                files["EXPORT_GAPS.md"] = (
                    "# Export gaps\n\nKeys the MetricFlow semantic model does not state, and why.\n\n"
                    + "".join(f"- {gap}\n" for gap in gaps))
            if notes:
                header.append(f"# Export notes ({len(notes)}): columns written as dimensions rather than summed, "
                              "or renamed; see EXPORT_NOTES.md.")
            if header:
                files["semantic_models.yml"] = "\n".join(header) + "\n" + files["semantic_models.yml"]
            return self._with_notes(files, model, eng, renamed)
        raise ExporterError(f"Unsupported semantic engine: {engine}")

    @classmethod
    def _foreign_entities(cls, model: SynthesizedModel) -> dict[tuple[str, str], tuple[str, bool]]:
        """(table, column) -> (entity name, joined) for every one-column foreign key.

        MetricFlow joins a foreign entity to the primary entity of the same
        name, and allows a name once per semantic model. So a table's first
        reference to a parent is named after the parent's primary entity and
        joins; a second reference to the same parent, or a reference to the
        table itself, would repeat a name the model already uses. It is named
        after its own column instead and does not join, and the join is a named
        gap (:meth:`metricflow_export_gaps`), never an invented one.
        """
        primary = {e.entity_name: cls._safe_semantic_name(e.primary_key[0])
                   for e in model.entities if len(e.primary_key) == 1}
        out: dict[tuple[str, str], tuple[str, bool]] = {}
        used: dict[str, set[str]] = {e.entity_name: ({primary[e.entity_name]} if e.entity_name in primary else set())
                                     for e in model.entities}
        keys = {e.entity_name: e.primary_key for e in model.entities}
        for rel in model.relationships:
            if len(rel.from_columns) != 1 or not rel.resolved:
                continue
            column = rel.from_columns[0]
            key = (rel.from_ref, column)
            if key in out or rel.from_ref not in used:
                continue
            if keys.get(rel.from_ref) == [column]:
                continue  # the primary entity itself; its join is the gap metricflow_export_gaps names
            wanted = primary.get(rel.to_ref, cls._safe_semantic_name(column))
            if wanted in used[rel.from_ref]:
                out[key] = (cls._safe_semantic_name(column), False)
            else:
                out[key] = (wanted, True)
            used[rel.from_ref].add(out[key][0])
        return out

    @classmethod
    def metricflow_export_gaps(cls, model: SynthesizedModel) -> list[str]:
        """Every key the MetricFlow semantic model cannot state, by name.

        A MetricFlow entity is one expression, so a composite foreign key is
        no join and a composite primary key no primary entity; and an entity
        has one type, so a one-column key that is also a foreign key is the
        primary entity and its join is not stated. Each was left out without a
        word until Sprint 8 Step 6.
        """
        def label(entity: str, columns: list[str]) -> str:
            return f"{entity}({', '.join(columns)})"

        one_column_fk = {(r.from_ref, r.from_columns[0]): r.to_ref for r in model.relationships
                         if len(r.from_columns) == 1}
        gaps = []
        for rel in model.relationships:
            where = f"{label(rel.from_ref, rel.from_columns)} -> {label(rel.to_ref, rel.to_columns)}"
            if not rel.resolved:
                gaps.append(f"{where}: unresolved, its columns are not chosen; no join")
            elif len(rel.from_columns) > 1:
                gaps.append(f"{where}: composite foreign key; a MetricFlow entity is one expression, "
                            "so this join is not in the semantic model")
        for entity in model.entities:
            key = entity.primary_key
            if len(key) > 1:
                gaps.append(f"{label(entity.entity_name, key)}: composite primary key; a MetricFlow entity is "
                            f"one expression, so the semantic model declares primary_entity "
                            f"'{entity.entity_name}' and nothing joins to it by this key")
            elif len(key) == 1 and (entity.entity_name, key[0]) in one_column_fk:
                parent = one_column_fk[(entity.entity_name, key[0])]
                gaps.append(f"{entity.entity_name}.{key[0]} -> {parent}: the primary key is also a foreign key; "
                            "an entity has one type, so it is the primary entity and this join is not in the "
                            "semantic model")
        parents = {(r.from_ref, r.from_columns[0]): r.to_ref for r in model.relationships
                   if len(r.from_columns) == 1 and r.resolved}
        for (table, column), (name, joined) in cls._foreign_entities(model).items():
            if not joined:
                parent = parents[(table, column)]
                why = ("it refers to its own table" if parent == table
                       else f"{table} already refers to {parent} by another column")
                gaps.append(f"{table}.{column} -> {parent}: {why}, and an entity name is used once per semantic "
                            f"model, so it is the entity '{name}' and this join is not in the semantic model")
        return gaps

    def _lookml_view(self, entity: EntitySchema, model: SynthesizedModel) -> str:
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
            # Keys, foreign keys and codes are not summed (dimension_reason).
            if (col.is_metric or self._is_numeric(col)) and self.dimension_reason(col, entity, model) is None:
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
        """The semantic layer as YAML (:meth:`_metricflow_document`)."""
        document, _ = self._metricflow_document(model)
        return yaml.safe_dump(document, sort_keys=False, default_flow_style=False)

    def _metricflow_document(self, model: SynthesizedModel) -> tuple[dict[str, object], list[str]]:
        """Emit a dbt semantic layer that ``dbt parse`` accepts (B1), and the
        dimensions it renamed so the export's notes can say so.

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
        # A composite one is not in the semantic model, and is a named gap
        # (``metricflow_export_gaps``), never a silent omission.
        fk_parent: dict[tuple[str, str], str] = {}
        for rel in model.relationships:
            if len(rel.from_columns) == 1:
                fk_parent[(rel.from_ref, rel.from_columns[0])] = rel.to_ref

        # Each entity's primary-entity name, which is its primary-key column,
        # for a one-column key only. A composite key is one identity over
        # several columns, which an entity (one expression) cannot state: such
        # a semantic model declares ``primary_entity`` instead, and its key
        # columns are dimensions or foreign entities (Sprint 8 Step 6). Until
        # then each key column was emitted as a primary entity.
        primary_entity_name: dict[str, str] = {}
        for entity in model.entities:
            if len(entity.primary_key) == 1:
                primary_entity_name[entity.entity_name] = self._safe_semantic_name(entity.primary_key[0])

        semantic_models: list[dict[str, Any]] = []
        # Each one-column foreign key's entity name, and whether it joins.
        foreign = self._foreign_entities(model)

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

                if entity.primary_key == [col.name]:
                    entities_block.append(
                        {"name": safe_name, "type": "primary", "expr": col.name}
                    )
                elif parent is not None:
                    entities_block.append(
                        {
                            # The parent's primary entity, not the local column;
                            # a second reference to one parent, or one to itself,
                            # is named after its column (_foreign_entities).
                            "name": foreign.get((entity.entity_name, col.name),
                                                (primary_entity_name.get(parent, safe_name), True))[0],
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
                elif col.is_primary_key:
                    # A column of a composite key: an identifier, never summed.
                    dimensions.append(
                        {"name": safe_name, "type": "categorical", "expr": col.name}
                    )
                elif (col.is_metric or self._is_numeric(col)) and self.dimension_reason(col, entity, model) is None:
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

        renamed = self._name_as_metricflow_requires(semantic_models)
        renamed += self._rename_dimensions_named_as_entities(semantic_models)
        renamed += self._rename_dimensions_repeated_under_one_entity(semantic_models)
        renamed += self._rename_repeated_measures(semantic_models)
        # One metric per measure, made from the final names; dbt requires a label on every metric.
        metrics = [{"name": str(m["name"]), "label": str(m["name"]).replace("_", " ").strip().title(),
                    "type": "simple", "type_params": {"measure": str(m["name"])}}
                   for sm in semantic_models for m in sm.get("measures", [])]
        document: dict[str, object] = {"semantic_models": semantic_models}
        if metrics:
            document["metrics"] = metrics
        return document, renamed

    #: MetricFlow's rule for every name in a semantic manifest.
    _METRICFLOW_NAME = re.compile(r"^[a-z](?!.*__)[a-z0-9_]*[a-z0-9]$")

    @classmethod
    def _snake(cls, name: str) -> str:
        words = [w.lower() for w in cls._NAME_WORD.findall(name)]
        snake = "_".join(words) or "x"
        return snake if snake[0].isalpha() and len(snake) > 1 else f"c_{snake}"

    @classmethod
    def _name_as_metricflow_requires(cls, semantic_models: list[dict[str, Any]]) -> list[str]:
        """Write every name MetricFlow would refuse in lower snake case; say so.

        MetricFlow names are lower-case letters, digits and underscores, and an
        imported schema's are the source's own (``AWBuildVersion``). Only a
        name that breaks the rule changes, so a reference model's names stay as
        they are; the same name always becomes the same new one, so a foreign
        entity still matches its parent's primary entity. Each ``expr`` keeps
        the column's own name, and the dbt model reference is untouched. Two
        names that would meet are told apart by a suffix, and each is listed.
        """
        mapping: dict[str, str] = {}

        def rename(name: object) -> str:
            text = str(name)
            if cls._METRICFLOW_NAME.match(text):
                return text
            return mapping.setdefault(text, cls._snake(text))

        notes: list[str] = []
        for sm in semantic_models:
            sm["name"] = rename(sm["name"])
            if "primary_entity" in sm:
                sm["primary_entity"] = rename(sm["primary_entity"])
            taken: dict[str, str] = {}
            final: dict[str, str] = {}
            for block in ("entities", "dimensions", "measures"):
                for item in sm.get(block, []):
                    old = str(item["name"])
                    new = rename(old)
                    if block != "entities":  # an entity name is shared by design; the others are the model's own
                        base, n = new, 2
                        while new in taken and taken[new] != item["name"]:
                            new = f"{base}_{n}"
                            n += 1
                        if new != base:
                            notes.append(f"{sm['name']}.{item['name']}: named '{new}', because '{base}' is taken "
                                         "in this semantic model")
                        taken[new] = old
                    if block == "dimensions":
                        final[old] = new
                    item["name"] = new
            defaults = sm.get("defaults")
            if isinstance(defaults, dict) and defaults.get("agg_time_dimension"):
                old_default = str(defaults["agg_time_dimension"])
                defaults["agg_time_dimension"] = final.get(old_default, rename(old_default))
        if mapping:
            example = next(iter(mapping.items()))
            notes.insert(0, f"{len(mapping)} names are written in lower snake case, as MetricFlow requires (for "
                            f"example '{example[0]}' as '{example[1]}'); each expr keeps the column's own name")
        return notes

    @staticmethod
    def _rename_repeated_measures(semantic_models: list[dict[str, Any]]) -> list[str]:
        """Rename a measure whose name another semantic model already uses; say which.

        Measure and metric names are unique across a manifest, and
        ``total_<column>`` repeats wherever two tables share a column name
        (AdventureWorks' ``StandardCost`` in ``Product`` and
        ``ProductCostHistory``). The first keeps its name; each later one
        becomes ``<table>_<name>``. Metrics are made from the measures after
        every rename, so each follows its measure.
        """
        seen: set[str] = set()
        renamed = []
        for sm in semantic_models:
            for measure in sm.get("measures", []):
                old = str(measure["name"])
                if old in seen:
                    new = f"{sm['name']}_{old}"
                    measure["name"] = new
                    renamed.append(f"{sm['name']}.{measure['expr']}: measure named '{new}', because '{old}' is "
                                   "a measure of another semantic model")
                seen.add(str(measure["name"]))
        return renamed

    @staticmethod
    def _rename_dimensions_repeated_under_one_entity(semantic_models: list[dict[str, Any]]) -> list[str]:
        """Rename a dimension that repeats under a primary entity another
        semantic model shares; say which.

        MetricFlow addresses a dimension by its primary entity and its name,
        so the pair must be unique across the manifest. Tables whose key is the
        same column (AdventureWorks' ``Person``, ``Employee``, ``Store`` and
        ``Vendor`` are all keyed by ``BusinessEntityID``) repeat column names
        such as ``ModifiedDate`` under one entity. The first keeps its name;
        each later one becomes ``<table>_<column>``, its ``expr`` unchanged.
        """
        seen: set[tuple[str, str]] = set()
        renamed = []
        for sm in semantic_models:
            primary = next((str(e["name"]) for e in sm.get("entities", []) if e.get("type") == "primary"),
                           str(sm.get("primary_entity", "")))
            for dimension in sm.get("dimensions", []):
                pair = (primary, str(dimension["name"]))
                if pair in seen:
                    old, new = dimension["name"], f"{sm['name']}_{dimension['name']}"
                    dimension["name"] = new
                    defaults = sm.get("defaults")
                    if isinstance(defaults, dict) and defaults.get("agg_time_dimension") == old:
                        defaults["agg_time_dimension"] = new
                    renamed.append(f"{sm['name']}.{dimension['expr']}: dimension named '{new}', because '{old}' "
                                   f"is already a dimension of the entity '{primary}' in another semantic model")
                seen.add((primary, str(dimension["name"])))
        return renamed

    @staticmethod
    def _rename_dimensions_named_as_entities(semantic_models: list[dict[str, Any]]) -> list[str]:
        """Rename each dimension whose name is an entity elsewhere; say which.

        MetricFlow requires one name to be one kind of element across the
        whole manifest. A column of a composite foreign key cannot be a join
        (an entity is one expression), so it is a dimension, while the same
        name is a primary entity in the table it refers to: AdventureWorks'
        ``SalesOrderDetail.ProductID`` against ``Product``. ``dbt parse``
        refuses that once the manifest has measures. The dimension becomes
        ``<Table>_<Column>``, its ``expr`` still the column, and no join is
        invented (owner, 2026-09-30). ``defaults.agg_time_dimension`` follows
        the rename, as it does for a reserved-granularity name.
        """
        entity_names = {str(e["name"]) for sm in semantic_models for e in sm.get("entities", [])}
        entity_names |= {str(sm["primary_entity"]) for sm in semantic_models if "primary_entity" in sm}
        renamed = []
        for sm in semantic_models:
            for dimension in sm.get("dimensions", []):
                if dimension["name"] in entity_names:
                    old, new = dimension["name"], f"{sm['name']}_{dimension['name']}"
                    dimension["name"] = new
                    defaults = sm.get("defaults")
                    if isinstance(defaults, dict) and defaults.get("agg_time_dimension") == old:
                        defaults["agg_time_dimension"] = new
                    renamed.append(f"{sm['name']}.{dimension['expr']}: dimension named '{new}', because "
                                   f"'{old}' is an entity elsewhere in the semantic model")
        return renamed


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
        reconciliation: str | None = None,
        statuses: Mapping[tuple[str, str | None, str], str] | None = None,
        levels: Mapping[uuid.UUID, str] | None = None,
    ) -> dict[str, str]:
        """The data dictionary (``app.services.data_dictionary``).

        ``reconciliation`` is the source model's import status
        (``reconciled``, ``unreconciled``, or None when it was not imported);
        every format states it, and an unreconciled source says so first.
        ``statuses`` are the fields' attested statuses and ``levels`` the
        workspace's classification level names, by id.
        """
        from app.services import data_dictionary

        fmt = dictionary_format.lower()
        doc = data_dictionary.build(model, dataset_name, reconciliation, statuses, levels)
        if fmt in ("markdown", "md"):
            return {"data_dictionary.md": data_dictionary.to_markdown(doc)}
        if fmt == "html":
            return {"data_dictionary.html": data_dictionary.to_html(doc)}
        if fmt == "json":
            return {"data_dictionary.json": data_dictionary.to_json(doc)}
        if fmt == "csv":
            return data_dictionary.to_csv(doc)
        raise ExporterError(f"Unsupported dictionary format: {dictionary_format}")

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
        """The shared type family: money types are numeric, a one-bit BIT is not."""
        return type_family(col.data_type) == "numeric"

    # ---------------------------------------------------------------------
    # Which numeric columns are summed (MetricFlow, Cube, LookML)
    # ---------------------------------------------------------------------
    #: A word anywhere in a name that makes an integer read as a code.
    _CODE_WORDS: ClassVar[frozenset[str]] = frozenset({
        "status", "code", "type", "flag", "kind", "category", "class", "indicator", "ind", "revision",
        "version", "rank", "priority", "tier", "grade", "level",
    })
    #: A last word that makes an integer read as an identifier.
    _ID_WORDS: ClassVar[frozenset[str]] = frozenset({
        "id", "key", "sk", "fk", "pk", "number", "no", "num", "nbr", "seq", "sequence",
    })
    #: A CHECK allowing at most this many values makes a column a code.
    _SMALL_SET = 20
    _NAME_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
    _IN_LIST = re.compile(r"\bIN\s*\(([^()]*)\)", re.IGNORECASE)
    _BETWEEN = re.compile(r"\bBETWEEN\s*\(?\s*(-?\d+)\s*\)?\s*AND\s*\(?\s*(-?\d+)", re.IGNORECASE)
    _LOWER_BOUND = re.compile(r">\s*(=?)\s*\(?\s*(-?\d+)\s*\)?(?!\s*[.\d])")
    _UPPER_BOUND = re.compile(r"<\s*(=?)\s*\(?\s*(-?\d+)\s*\)?(?!\s*[.\d])")

    @classmethod
    def _small_set_check(cls, col: ColumnSchema, entity: EntitySchema) -> str | None:
        """A one-column CHECK allowing few values (an IN list, or a narrow
        integer range), as the model holds it; None if there is none."""
        for check in entity.check_constraints:
            if check.columns != [col.name]:
                continue
            listed = cls._IN_LIST.search(check.expression)
            if listed and 0 < len([v for v in listed.group(1).split(",") if v.strip()]) <= cls._SMALL_SET:
                return check.expression
            between = cls._BETWEEN.search(check.expression)
            if between:
                low, high = int(between.group(1)), int(between.group(2))
            else:
                lower, upper = cls._LOWER_BOUND.search(check.expression), cls._UPPER_BOUND.search(check.expression)
                if not (lower and upper):
                    continue
                low = int(lower.group(2)) + (0 if lower.group(1) else 1)
                high = int(upper.group(2)) - (0 if upper.group(1) else 1)
            if 0 <= high - low < cls._SMALL_SET:
                return check.expression
        return None

    @classmethod
    def dimension_reason(cls, col: ColumnSchema, entity: EntitySchema, model: SynthesizedModel) -> str | None:
        """Why a numeric column is never a summed measure, or None if it is one.

        Keys and foreign keys identify rows; summing them means nothing. An
        integer column with permissible values, a CHECK allowing a small set,
        or a name that reads as a code or an identifier (``Status``,
        ``RevisionNumber``) is a code, grouped by rather than added. A column a
        person declared a metric is a measure unless it is a key. Every choice
        is listed in the export's notes (:meth:`semantic_notes`), so none is
        silent.
        """
        if not cls._is_numeric(col):
            return None
        if col.is_primary_key or col.name in entity.primary_key:
            return "a primary-key column"
        if col.is_foreign_key or any(rel.from_ref == entity.entity_name and col.name in rel.from_columns
                                     for rel in model.relationships):
            return "a foreign-key column"
        if col.is_metric or not is_integer_type(col.data_type):
            return None
        if col.permissible_values:
            return "an integer with permissible values"
        check = cls._small_set_check(col, entity)
        if check is not None:
            return f"an integer whose CHECK allows few values: {check}"
        words = [w.lower() for w in cls._NAME_WORD.findall(col.name)]
        code = next((w for w in words if w in cls._CODE_WORDS), None)
        if code is not None:
            return f"an integer whose name reads as a code ('{code}')"
        if words and words[-1] in cls._ID_WORDS:
            return f"an integer whose name reads as an identifier ('{words[-1]}')"
        return None

    def semantic_notes(self, model: SynthesizedModel, engine: str) -> list[str]:
        """Every numeric column written as a dimension rather than summed, and why.

        For MetricFlow only tables with an aggregation time column, since a
        table without one declares no measures at all.
        """
        notes = []
        for entity in model.entities:
            if engine == "metricflow" and not entity.agg_time_column:
                continue
            for col in entity.columns:
                reason = self.dimension_reason(col, entity, model)
                if reason is not None:
                    notes.append(f"{entity.entity_name}.{col.name} ({col.data_type}): not summed as a measure; "
                                 f"{reason}")
        return notes

    def _with_notes(self, files: dict[str, str], model: SynthesizedModel, engine: str,
                    extra: list[str] | None = None) -> dict[str, str]:
        notes = self.semantic_notes(model, engine) + (extra or [])
        if notes:
            files["EXPORT_NOTES.md"] = (
                "# Export notes\n\nHow columns are written, and why: numeric columns written as dimensions "
                "rather than summed measures, and any dimension renamed.\n\n"
                + "".join(f"- {note}\n" for note in notes))
        return files

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
