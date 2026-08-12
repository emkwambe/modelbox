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
import logging
import re
import string
import zlib
from dataclasses import dataclass, field
from random import Random

import networkx as nx

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services.graph_engine import GraphEngine

logger = logging.getLogger(__name__)

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
        # Values already used by a declared-unique column, per entity+column.
        taken: dict[tuple[str, str], set[object]] = {}

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
                        # A foreign key must repeat a parent value, so it is
                        # deliberately exempt from the distinctness pass below:
                        # referential integrity outranks a declared UNIQUE.
                        row[col.name] = self._rng(ename, col.name, i).choice(
                            pools[target]
                        )
                        continue
                    if col.is_primary_key:
                        value = self._fit(self._pk_value(entity, col, i), col)
                    else:
                        value = self._fit(self._value(entity, col, i), col)
                    if col.is_unique or col.is_primary_key:
                        bucket = taken.setdefault(key, set())
                        value = self._distinct(value, col, bucket)
                        bucket.add(value)
                    row[col.name] = value
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
        """Generate one value for a column.

        **Declared constraints outrank heuristics.** That ordering is the whole
        fix for H1, and it is a rule rather than a set of special cases. The
        generator carries name-based guesses — a column called ``status`` used
        to draw from a hard-coded ``ACTIVE/INACTIVE/PENDING`` vocabulary — and
        those guesses were beating the model's own declarations. A model
        declaring ``CHECK (status IN ('PENDING','DONE'))`` got ``INACTIVE``.

        That is worse than having no constraint awareness, because it looks
        deliberate: the generator did not overlook the contract, it disagreed
        with it and won. Anything the IR states is now consulted first, and the
        heuristics only decide what the IR leaves open.
        """
        name = col.name.lower()
        t = col.data_type.upper()
        rng = self._rng(entity.entity_name, col.name, i)

        def pick(seq: list[str]) -> str:
            return seq[rng.randrange(len(seq))]

        # -- declared constraints, in order of how tightly they bind ---------
        allowed = self._check_enum(col.check_expression)
        if allowed:
            return pick(allowed)

        if col.regex_pattern:
            sample = self._from_pattern(col.regex_pattern, rng)
            if sample is not None:
                return sample
            # Unsupported pattern: fall through rather than emit something
            # that silently claims to satisfy it. The value will violate the
            # contract, and the harness says so, which is the honest outcome.
            logger.warning(
                "Cannot generate a value matching %r for %s.%s; falling back.",
                col.regex_pattern,
                entity.entity_name,
                col.name,
            )

        numeric = self._numeric_value(col, rng)
        if numeric is not None:
            return numeric

        # -- name-driven heuristics, for whatever the IR left open -----------
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

    # -- declared-constraint generators -------------------------------------
    @staticmethod
    def _check_enum(expression: str | None) -> list[str] | None:
        """Allowed literals from a simple ``col IN ('a', 'b')`` CHECK.

        Deliberately narrow. A value generator cannot evaluate an arbitrary SQL
        predicate, and pretending to would be untested handling that fails
        silently on the first expression it cannot parse. An enumeration is
        unambiguous, is the form that actually occurs, and is exactly where the
        generator's own hard-coded vocabularies used to contradict the model.
        Anything else falls through to the heuristics.
        """
        if not expression or " IN " not in expression.upper():
            return None
        literals = re.findall(r"'([^']*)'", expression)
        return literals or None

    @staticmethod
    def _from_pattern(pattern: str, rng: Random) -> str | None:
        """A value matching a simple anchored regex, or None if unsupported.

        Supports literals and the character classes that appear in practice —
        ``[A-Z]``, ``[a-z]``, ``[0-9]``, ``\\d``, ``\\w`` — with ``{n}`` and
        ``{n,m}`` repetition. The result is verified with ``fullmatch`` before
        being returned, so an incomplete implementation reports failure rather
        than emitting a value that merely looks plausible.
        """
        body = pattern.strip().removeprefix("^").removesuffix("$")

        alphabets = {
            "A-Z": string.ascii_uppercase,
            "a-z": string.ascii_lowercase,
            "0-9": string.digits,
            "A-Za-z": string.ascii_letters,
            "A-Za-z0-9": string.ascii_letters + string.digits,
        }
        token = re.compile(
            r"\[([^\]]+)\]\{(\d+)(?:,(\d+))?\}"   # [A-Z]{3} / [A-Z]{3,5}
            r"|\[([^\]]+)\]"                        # [A-Z]
            r"|\\([dw])\{(\d+)(?:,(\d+))?\}"       # \d{4}
            r"|\\([dw])"                            # \d
            r"|([A-Za-z0-9_@.\-/ ])"                # a literal
        )
        out: list[str] = []
        position = 0
        for match in token.finditer(body):
            if match.start() != position:
                return None  # something unsupported sat between tokens
            position = match.end()
            cls, lo, hi, bare_cls, esc, esc_lo, esc_hi, bare_esc, literal = (
                match.groups()
            )
            if literal is not None:
                out.append(literal)
                continue
            if bare_cls is not None:
                cls, lo, hi = bare_cls, "1", None
            if bare_esc is not None:
                esc, esc_lo, esc_hi = bare_esc, "1", None
            if esc is not None:
                cls = "0-9" if esc == "d" else "A-Za-z0-9"
                lo, hi = esc_lo, esc_hi
            alphabet = alphabets.get(cls or "")
            if alphabet is None:
                return None
            count = int(lo or 1)
            if hi:
                count = rng.randint(count, int(hi))
            out.append("".join(alphabet[rng.randrange(len(alphabet))]
                               for _ in range(count)))
        if position != len(body):
            return None

        candidate = "".join(out)
        return candidate if re.fullmatch(pattern, candidate) else None

    def _numeric_value(self, col: ColumnSchema, rng: Random) -> float | int | None:
        """A number honouring declared bounds *and* declared precision/scale.

        These are three independent constraints, and a value can satisfy one
        while violating another: ``6332.15`` is inside no declared range, has
        six significant digits against a declared five, and only the scale
        happens to be right. Fixing the range alone would leave a value that
        still cannot be inserted.
        """
        upper = col.data_type.upper()
        is_decimal = any(
            tok in upper for tok in ("NUMERIC", "DECIMAL", "NUMBER", "FLOAT",
                                     "DOUBLE", "REAL", "MONEY")
        )
        is_integer = self._is_int(upper)
        if not (is_decimal or is_integer):
            return None
        if col.min_value is None and col.max_value is None and not is_decimal:
            return None  # unconstrained integers keep their existing behaviour

        precision, scale = self._precision_scale(col.data_type)
        low = col.min_value if col.min_value is not None else 0.0
        high = col.max_value if col.max_value is not None else None
        if high is None:
            # The widest value the declared precision admits, so a bare
            # NUMERIC(5,2) never produces six digits.
            high = (
                float(10 ** (precision - scale)) - (10.0 ** -scale)
                if precision is not None
                else 10_000.0
            )
        # Contradictory bounds are a lint finding about the model, not ours.
        low = min(low, high)

        if is_integer and scale in (None, 0):
            return rng.randint(int(low), max(int(low), int(high)))
        value = rng.uniform(low, high)
        return round(value, scale if scale is not None else 2)

    @staticmethod
    def _precision_scale(data_type: str) -> tuple[int | None, int | None]:
        match = re.search(r"\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)", data_type)
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2) or 0)

    @staticmethod
    def _declared_length(data_type: str) -> int | None:
        match = re.search(r"(?:VAR)?CHAR\s*\(\s*(\d+)\s*\)", data_type, re.IGNORECASE)
        return int(match.group(1)) if match else None

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

    def _distinct(
        self, value: object, col: ColumnSchema, taken: set[object]
    ) -> object:
        """Force a declared-unique value to be distinct within its entity.

        This exists because the length clamp can *create* duplicates: the
        fallback ``external_ref_1 … external_ref_10`` is distinct until a
        declared ``VARCHAR(12)`` truncates every row of it to ``external_ref``.
        Clamping and uniqueness are two declared constraints that pull against
        each other, so satisfying one has to be done knowing the other.
        """
        if value not in taken:
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            candidate = value
            while candidate in taken:
                candidate += 1
            return candidate
        if not isinstance(value, str):
            return value

        limit = self._declared_length(col.data_type)
        for n in range(1, len(taken) + 2):
            suffix = str(n)
            base = value if limit is None else value[: max(0, limit - len(suffix))]
            candidate = f"{base}{suffix}"
            if candidate not in taken:
                return candidate
        return value  # unsatisfiable within the declared length

    def _fit(self, value: object, col: ColumnSchema) -> object:
        """Truncate a string to the column's declared length.

        Applied at the single point every generated value passes through, so a
        new heuristic cannot reintroduce the overflow. The defect was
        systematic rather than incidental: the fallback emitted
        ``f"{col.name}_{i}"``, so the longer the column name the worse the
        overflow, and `icd10_code VARCHAR(10)` was one instance of it.

        Values produced from a declared regex are left alone — truncating one
        would break the pattern it was generated to satisfy. A pattern that
        cannot fit its own column is a contradiction in the model, and belongs
        to the linter rather than here.
        """
        limit = self._declared_length(col.data_type)
        if limit is None or not isinstance(value, str) or len(value) <= limit:
            return value
        if col.regex_pattern:
            return value
        return value[:limit]

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
