"""Synthetic seed-data generator (FR-2.4).

Produces referentially-intact mock datasets from a :class:`SynthesizedModel`:

* entities are populated in topological order (parents before children) so
  foreign keys always resolve to a real parent row,
* values are chosen by column-name/type heuristics (emails, names, numerics,
  dates, booleans, surrogate keys, …),
* output is emitted as SQL ``INSERT`` statements or a per-entity CSV bundle.

Pure, stateless, and **dependency-free** — no Faker, no DB, no network — so it
stays air-gapped-safe and, given a fixed ``seed``, fully deterministic (the same
model always yields the same fixtures, which is what reproducible QA seeds want).
"""

from __future__ import annotations

import csv
import io
import zlib
from dataclasses import dataclass, field
from random import Random

import networkx as nx

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services.graph_engine import GraphEngine

_FIRST = ["Ava", "Noah", "Mia", "Liam", "Ivy", "Ezra", "Zoe", "Kai", "Nora", "Leo"]
_LAST = ["Kim", "Ono", "Diaz", "Bauer", "Cruz", "Frost", "Vance", "Reyes", "Sato", "Ali"]
_CITIES = ["Nairobi", "Lagos", "Cairo", "Accra", "Dar es Salaam", "Kigali", "Tunis"]
_COUNTRIES = ["Kenya", "Nigeria", "Egypt", "Ghana", "Tanzania", "Rwanda", "Tunisia"]
_STREETS = ["Baobab Ave", "Acacia Rd", "Nile St", "Savanna Way", "Harbor Blvd"]


@dataclass
class SeedResult:
    """A generated seed dataset."""

    files: dict[str, str] = field(default_factory=dict)
    generation_order: list[str] = field(default_factory=list)


class SyntheticSeedGenerator:
    """Generates FK-consistent synthetic rows for a model graph."""

    def __init__(self, dialect: str = "postgres", seed: int = 1337) -> None:
        self._dialect = dialect
        self._seed = seed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(
        self, model: SynthesizedModel, row_count: int, fmt: str = "sql_insert"
    ) -> SeedResult:
        order = self._generation_order(model)
        by_name = {e.entity_name: e for e in model.entities}

        # (child_entity, child_col) -> (parent_entity, parent_col)
        fk_target: dict[tuple[str, str], tuple[str, str]] = {}
        for rel in model.relationships:
            fe, fc = self._split(rel.from_ref)
            te, tc = self._split(rel.to_ref)
            if fc and tc:
                fk_target[(fe, fc)] = (te, tc)
        referenced = set(fk_target.values())

        pools: dict[tuple[str, str], list[object]] = {}
        rows_by_entity: dict[str, list[dict[str, object]]] = {}

        for ename in order:
            entity = by_name.get(ename)
            if entity is None:
                continue
            rows: list[dict[str, object]] = []
            for i in range(row_count):
                row: dict[str, object] = {}
                for col in entity.columns:
                    key = (ename, col.name)
                    target = fk_target.get(key)
                    if target is not None and pools.get(target):
                        row[col.name] = self._rng(ename, col.name, i).choice(
                            pools[target]
                        )
                    elif col.is_primary_key:
                        row[col.name] = self._pk_value(entity, col, i)
                    else:
                        row[col.name] = self._value(entity, col, i)
                # Cache any column another entity references (usually the PK).
                for col in entity.columns:
                    if (ename, col.name) in referenced:
                        pools.setdefault((ename, col.name), []).append(row[col.name])
                rows.append(row)
            rows_by_entity[ename] = rows

        present_order = [e for e in order if e in rows_by_entity]
        if fmt == "csv":
            files = self._render_csv(by_name, rows_by_entity, present_order)
        else:
            files = self._render_sql(by_name, rows_by_entity, present_order)
        return SeedResult(files=files, generation_order=present_order)

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------
    def _generation_order(self, model: SynthesizedModel) -> list[str]:
        graph = GraphEngine.build_graph(model.entities, model.relationships)
        try:
            return GraphEngine.topological_order(graph)
        except nx.NetworkXUnfeasible:
            # Cyclic FKs: fall back to declared order (FKs may be deferred).
            return [e.entity_name for e in model.entities]

    # ------------------------------------------------------------------
    # Value generation
    # ------------------------------------------------------------------
    def _rng(self, entity: str, col: str, i: int) -> Random:
        salt = zlib.crc32(f"{entity}|{col}|{i}".encode()) & 0xFFFFFFFF
        return Random(self._seed ^ salt)

    def _pk_value(self, entity: EntitySchema, col: ColumnSchema, i: int) -> object:
        t = col.data_type.upper()
        if "UUID" in t:
            r = self._rng(entity.entity_name, col.name, i)
            return "%08x-%04x-4%03x-%04x-%012x" % (
                r.getrandbits(32), r.getrandbits(16), r.getrandbits(12),
                r.getrandbits(16), r.getrandbits(48),
            )
        if self._is_int(t):
            return i + 1
        return f"{entity.entity_name}_{i + 1}"

    def _value(self, entity: EntitySchema, col: ColumnSchema, i: int) -> object:
        name = col.name.lower()
        t = col.data_type.upper()
        rng = self._rng(entity.entity_name, col.name, i)

        def pick(seq: list[str]) -> str:
            return seq[rng.randrange(len(seq))]

        # Name-driven heuristics take priority over raw type.
        if "email" in name:
            return f"{pick(_FIRST).lower()}.{pick(_LAST).lower()}{rng.randint(1, 999)}@example.com"
        if "first" in name and "name" in name:
            return pick(_FIRST)
        if "last" in name and "name" in name:
            return pick(_LAST)
        if name == "name" or name.endswith("_name") or "full_name" in name:
            return f"{pick(_FIRST)} {pick(_LAST)}"
        if "phone" in name:
            return f"+1-{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
        if "city" in name:
            return pick(_CITIES)
        if "country" in name:
            return pick(_COUNTRIES)
        if "address" in name or "street" in name:
            return f"{rng.randint(1, 9999)} {pick(_STREETS)}"
        if "status" in name:
            return pick(["ACTIVE", "INACTIVE", "PENDING"])
        if "tier" in name:
            return pick(["BRONZE", "SILVER", "GOLD", "PLATINUM"])

        # Type-driven fallbacks.
        if "BOOL" in t:
            return rng.random() < 0.5
        if any(tok in t for tok in ("TIMESTAMP", "DATETIME")):
            return self._timestamp(rng)
        if "DATE" in t:
            return self._date(rng)
        if any(
            tok in t
            for tok in ("NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "MONEY", "NUMBER")
        ):
            return round(rng.uniform(1, 10000), 2)
        if self._is_int(t):
            return rng.randint(1, 100000)
        return f"{col.name}_{i + 1}"

    @staticmethod
    def _is_int(t: str) -> bool:
        return any(tok in t for tok in ("INT", "SERIAL")) and "POINT" not in t

    @staticmethod
    def _date(rng: Random) -> str:
        return f"{rng.randint(2020, 2024)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"

    def _timestamp(self, rng: Random) -> str:
        return (
            f"{self._date(rng)} "
            f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_sql(
        self,
        by_name: dict[str, EntitySchema],
        rows_by_entity: dict[str, list[dict[str, object]]],
        order: list[str],
    ) -> dict[str, str]:
        chunks = [
            "-- Synthetic seed data generated by ModelBox AI (FR-2.4).",
            f"-- Generation order (FK-safe): {', '.join(order)}",
            "",
        ]
        for ename in order:
            entity = by_name[ename]
            cols = [c.name for c in entity.columns]
            rows = rows_by_entity[ename]
            if not rows:
                continue
            values = [
                "  (" + ", ".join(self._sql_literal(row[c]) for c in cols) + ")"
                for row in rows
            ]
            chunks.append(
                f"INSERT INTO {ename} ({', '.join(cols)}) VALUES\n"
                + ",\n".join(values)
                + ";\n"
            )
        return {f"seed_{self._dialect}.sql": "\n".join(chunks)}

    def _render_csv(
        self,
        by_name: dict[str, EntitySchema],
        rows_by_entity: dict[str, list[dict[str, object]]],
        order: list[str],
    ) -> dict[str, str]:
        files: dict[str, str] = {}
        for ename in order:
            entity = by_name[ename]
            cols = [c.name for c in entity.columns]
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            writer.writerow(cols)
            for row in rows_by_entity[ename]:
                writer.writerow([self._csv_cell(row[c]) for c in cols])
            files[f"{ename}.csv"] = buf.getvalue()
        return files

    @staticmethod
    def _sql_literal(value: object) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def _csv_cell(value: object) -> object:
        if isinstance(value, bool):
            return "true" if value else "false"
        return value

    @staticmethod
    def _split(ref: str) -> tuple[str, str]:
        parts = ref.split(".", 1)
        return (parts[0], parts[1] if len(parts) > 1 else "")
