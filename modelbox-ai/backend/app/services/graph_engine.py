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

import networkx as nx

from app.schemas.data_model import (
    EntitySchema,
    RelationshipSchema,
    ValidationIssue,
    ValidationReport,
)


class GraphEngine:
    """Builds and validates entity-relationship graphs with NetworkX."""

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
            for ref, side in ((rel.from_ref, "from"), (rel.to_ref, "to")):
                name = ref.split(".", 1)[0]
                if name not in entity_names:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="DANGLING_REF",
                            message=(
                                f"Relationship '{side}' references unknown "
                                f"entity '{name}'."
                            ),
                            entities=[name],
                        )
                    )

        is_valid = not any(issue.severity == "error" for issue in issues)
        return ValidationReport(is_valid=is_valid, issues=issues)
