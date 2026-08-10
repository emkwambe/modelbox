"""Graph parsing & validation engine.

Wraps NetworkX to turn a model's entities + relationships into a directed
graph, then runs the topological checks the canvas relies on (FR-2.3):

* cyclic foreign-key detection,
* missing-primary-key linting,
* dangling-reference detection,
* dependency layering / topological ordering (used by OBT denormalization and
  deterministic DDL emission order).

This is Component A from TRD §2.2. Business logic lives here as a reusable
service class — API handlers only orchestrate it.
"""

from __future__ import annotations

import re

import networkx as nx

from app.schemas.data_model import (
    EntitySchema,
    RelationshipSchema,
    ValidationIssue,
    ValidationReport,
)

# Governance/convention lint configuration (FR-2.3, Pick 1).
# Entity-type -> expected name prefix.
_PREFIX_BY_TYPE: dict[str, str] = {
    "FACT": "fact_",
    "DIMENSION": "dim_",
    "HUB": "hub_",
    "LINK": "lnk_",
    "SATELLITE": "sat_",
}
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_KEY_SUFFIXES = ("_id", "_sk", "_key", "_hk", "_pk")
# Column-name fragments that strongly imply personal data. Kept specific to
# avoid false positives — e.g. "ip_address" (not bare "ip", which would match
# zip/shipping/description/recipient).
_PII_PATTERNS = (
    "email",
    "ssn",
    "social_security",
    "phone",
    "dob",
    "date_of_birth",
    "birth_date",
    "credit_card",
    "passport",
    "iban",
    "ip_address",
)


class GraphEngine:
    """Builds and validates entity-relationship graphs with NetworkX."""

    @staticmethod
    def _split_ref(ref: str) -> tuple[str, str]:
        """Split an 'entity.column' reference into its parts."""
        parts = ref.split(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")

    @staticmethod
    def build_graph(
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> nx.DiGraph:
        """Construct a directed graph: nodes are entities, edges are FK refs.

        Edge direction follows the referential dependency ``from -> to``
        (child references parent), so a topological sort yields a valid
        creation/emission order.
        """
        graph: nx.DiGraph = nx.DiGraph()

        for entity in entities:
            graph.add_node(
                entity.entity_name,
                entity_type=entity.entity_type,
                column_count=len(entity.columns),
                has_primary_key=any(col.is_primary_key for col in entity.columns),
            )

        for rel in relationships:
            from_entity = rel.from_ref.split(".", 1)[0]
            to_entity = rel.to_ref.split(".", 1)[0]
            graph.add_edge(
                from_entity,
                to_entity,
                cardinality=rel.cardinality,
                from_ref=rel.from_ref,
                to_ref=rel.to_ref,
            )

        return graph

    @staticmethod
    def detect_cycles(graph: nx.DiGraph) -> list[list[str]]:
        """Return every simple cycle (circular FK chain) in the graph."""
        return [cycle for cycle in nx.simple_cycles(graph)]

    @staticmethod
    def topological_order(graph: nx.DiGraph) -> list[str]:
        """Return entity names in dependency order (parents before children).

        Raises ``networkx.NetworkXUnfeasible`` if the graph contains a cycle;
        callers should run :meth:`detect_cycles` first when that is possible.
        """
        # Reverse so referenced (parent) entities come first.
        return list(nx.topological_sort(graph.reverse(copy=False)))

    @staticmethod
    def dependency_layers(graph: nx.DiGraph) -> list[list[str]]:
        """Group entities into dependency layers for staged processing.

        Layer 0 has no dependencies; each subsequent layer depends only on
        earlier layers. Used by OBT flattening and parallel DDL generation.
        """
        return [sorted(layer) for layer in nx.topological_generations(graph.reverse(copy=False))]

    def validate(
        self,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> ValidationReport:
        """Run all topological + structural lints, returning a report (FR-2.3)."""
        graph = self.build_graph(entities, relationships)
        issues: list[ValidationIssue] = []

        entity_names = {entity.entity_name for entity in entities}

        # 1. Cyclic foreign-key references (TS-02).
        for cycle in self.detect_cycles(graph):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="CYCLIC_FK",
                    message=f"Circular foreign-key reference: {' -> '.join(cycle)} -> {cycle[0]}",
                    entities=cycle,
                )
            )

        # 2. Missing primary keys.
        for entity in entities:
            if not any(col.is_primary_key for col in entity.columns):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MISSING_PK",
                        message=f"Entity '{entity.entity_name}' has no primary key.",
                        entities=[entity.entity_name],
                    )
                )

        # 3. Relationships pointing at unknown entities.
        for rel in relationships:
            from_entity, from_col = self._split_ref(rel.from_ref)
            to_entity, to_col = self._split_ref(rel.to_ref)

            # A foreign key on an existing entity pointing at a missing target.
            if to_entity not in entity_names:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DANGLING_REF",
                        message=(
                            f"Foreign key '{from_entity}.{from_col}' references "
                            f"unknown entity '{to_entity}'."
                        ),
                        # Include the source entity so its node highlights.
                        entities=[e for e in (from_entity, to_entity) if e],
                        entity_name=from_entity or None,
                        column_name=from_col or None,
                    )
                )

            # The relationship originates from an entity that does not exist.
            if from_entity not in entity_names:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DANGLING_REF",
                        message=(
                            f"Relationship source references unknown entity "
                            f"'{from_entity}'."
                        ),
                        entities=[from_entity] if from_entity else [],
                        entity_name=from_entity or None,
                        column_name=from_col or None,
                    )
                )

        # 4–8. Governance & convention lints (Pick 1). These are advisory
        # warnings — they never invalidate a model, only nudge quality.
        issues.extend(self._lint_naming(entities))
        issues.extend(self._lint_grain(entities))
        issues.extend(self._lint_descriptions(entities))
        issues.extend(self._lint_pii(entities))
        issues.extend(self._lint_orphans(entities, relationships))
        issues.extend(self._lint_fan_out(entities, relationships))
        issues.extend(self._lint_sla(entities))

        is_valid = not any(issue.severity == "error" for issue in issues)
        return ValidationReport(is_valid=is_valid, issues=issues)

    # -----------------------------------------------------------------------
    # Governance & convention lints (FR-2.3, Pick 1)
    # -----------------------------------------------------------------------
    @staticmethod
    def _entity_type(entity: EntitySchema) -> str:
        """Normalize the entity type to its string value (enum or str)."""
        etype = entity.entity_type
        return etype.value if hasattr(etype, "value") else str(etype)

    @classmethod
    def _lint_naming(cls, entities: list[EntitySchema]) -> list[ValidationIssue]:
        """NAMING_CONVENTION — snake_case + type prefix + key suffix checks."""
        issues: list[ValidationIssue] = []
        for entity in entities:
            name = entity.entity_name
            if not _SNAKE_RE.match(name):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="NAMING_CONVENTION",
                        message=f"Entity '{name}' is not snake_case.",
                        entities=[name],
                        entity_name=name,
                    )
                )
            prefix = _PREFIX_BY_TYPE.get(cls._entity_type(entity))
            if prefix and not name.startswith(prefix):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="NAMING_CONVENTION",
                        message=(
                            f"{cls._entity_type(entity)} entity '{name}' should be "
                            f"prefixed '{prefix}'."
                        ),
                        entities=[name],
                        entity_name=name,
                    )
                )
            for column in entity.columns:
                if not _SNAKE_RE.match(column.name):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="NAMING_CONVENTION",
                            message=f"Column '{name}.{column.name}' is not snake_case.",
                            entities=[name],
                            entity_name=name,
                            column_name=column.name,
                        )
                    )
                # A bare 'id' is an accepted surrogate key; otherwise a PK should
                # carry a key suffix.
                if (
                    column.is_primary_key
                    and column.name != "id"
                    and not column.name.endswith(_KEY_SUFFIXES)
                ):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="NAMING_CONVENTION",
                            message=(
                                f"Primary key '{name}.{column.name}' should end with a "
                                f"key suffix ({', '.join(_KEY_SUFFIXES)})."
                            ),
                            entities=[name],
                            entity_name=name,
                            column_name=column.name,
                        )
                    )
        return issues

    @classmethod
    def _lint_grain(cls, entities: list[EntitySchema]) -> list[ValidationIssue]:
        """MISSING_GRAIN — FACT entities must declare a business grain."""
        issues: list[ValidationIssue] = []
        for entity in entities:
            if cls._entity_type(entity) == "FACT" and not (
                entity.grain and entity.grain.strip()
            ):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MISSING_GRAIN",
                        message=(
                            f"Fact entity '{entity.entity_name}' has no declared grain."
                        ),
                        entities=[entity.entity_name],
                        entity_name=entity.entity_name,
                    )
                )
        return issues

    @staticmethod
    def _lint_descriptions(entities: list[EntitySchema]) -> list[ValidationIssue]:
        """MISSING_DESCRIPTION — entities and columns should be documented."""
        issues: list[ValidationIssue] = []
        for entity in entities:
            name = entity.entity_name
            if not (entity.description and entity.description.strip()):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MISSING_DESCRIPTION",
                        message=f"Entity '{name}' has no description.",
                        entities=[name],
                        entity_name=name,
                    )
                )
            undocumented = [
                c.name
                for c in entity.columns
                if not (c.description and c.description.strip())
            ]
            if undocumented:
                shown = ", ".join(undocumented[:6])
                more = "…" if len(undocumented) > 6 else ""
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MISSING_DESCRIPTION",
                        message=(
                            f"Entity '{name}' has {len(undocumented)} undocumented "
                            f"column(s): {shown}{more}."
                        ),
                        entities=[name],
                        entity_name=name,
                    )
                )
        return issues

    @staticmethod
    def _lint_pii(entities: list[EntitySchema]) -> list[ValidationIssue]:
        """PII_EXPOSURE — columns that look like PII but are not classified.

        Flags the governance *gap* (unclassified personal data), not correctly
        tagged PII — so well-tagged models stay quiet.
        """
        issues: list[ValidationIssue] = []
        for entity in entities:
            for column in entity.columns:
                lowered = column.name.lower()
                looks_like_pii = any(p in lowered for p in _PII_PATTERNS)
                if looks_like_pii and not column.is_pii:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="PII_EXPOSURE",
                            message=(
                                f"Column '{entity.entity_name}.{column.name}' looks "
                                f"like PII but is not classified (set is_pii/pii_type)."
                            ),
                            entities=[entity.entity_name],
                            entity_name=entity.entity_name,
                            column_name=column.name,
                        )
                    )
        return issues

    @classmethod
    def _lint_fan_out(
        cls,
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> list[ValidationIssue]:
        """FAN_OUT_RISK — relationships that can duplicate rows and inflate
        aggregated measures in a semantic layer.

        Flags the two classic traps: many-to-many (``N:M``) relationships, and
        joins between two ``FACT`` entities (fact-to-fact / chasm trap).
        """
        types = {e.entity_name: cls._entity_type(e) for e in entities}
        issues: list[ValidationIssue] = []
        for rel in relationships:
            from_entity = rel.from_ref.split(".", 1)[0]
            to_entity = rel.to_ref.split(".", 1)[0]
            cardinality = rel.cardinality
            card_value = (
                cardinality.value
                if hasattr(cardinality, "value")
                else str(cardinality)
            )
            reason: str | None = None
            if card_value == "N:M":
                reason = "many-to-many relationship"
            elif types.get(from_entity) == "FACT" and types.get(to_entity) == "FACT":
                reason = "join between two FACT entities"
            if reason is None:
                continue
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="FAN_OUT_RISK",
                    message=(
                        f"Fan-out risk: {reason} ({from_entity} -> {to_entity}) "
                        f"can duplicate rows and inflate aggregated measures."
                    ),
                    entities=[e for e in (from_entity, to_entity) if e],
                    entity_name=from_entity or None,
                )
            )
        return issues

    @staticmethod
    def _lint_sla(entities: list[EntitySchema]) -> list[ValidationIssue]:
        """MISSING_SLA — a critical/important asset with no freshness SLA."""
        critical = {"TIER_1_CRITICAL", "TIER_2_IMPORTANT"}
        issues: list[ValidationIssue] = []
        for entity in entities:
            tier = entity.tier
            tier_value = tier.value if hasattr(tier, "value") else str(tier)
            if tier_value in critical and not (
                entity.freshness_sla and entity.freshness_sla.strip()
            ):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="MISSING_SLA",
                        message=(
                            f"{tier_value} asset '{entity.entity_name}' has no "
                            f"declared freshness SLA."
                        ),
                        entities=[entity.entity_name],
                        entity_name=entity.entity_name,
                    )
                )
        return issues

    @staticmethod
    def _lint_orphans(
        entities: list[EntitySchema],
        relationships: list[RelationshipSchema],
    ) -> list[ValidationIssue]:
        """ORPHAN_ENTITY — isolated nodes in a multi-entity model."""
        # A single-table model (e.g. OBT) is legitimately relationship-free.
        if len(entities) <= 1:
            return []
        connected: set[str] = set()
        for rel in relationships:
            connected.add(rel.from_ref.split(".", 1)[0])
            connected.add(rel.to_ref.split(".", 1)[0])
        issues: list[ValidationIssue] = []
        for entity in entities:
            if entity.entity_name not in connected:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="ORPHAN_ENTITY",
                        message=(
                            f"Entity '{entity.entity_name}' has no relationships to "
                            f"other entities."
                        ),
                        entities=[entity.entity_name],
                        entity_name=entity.entity_name,
                    )
                )
        return issues
