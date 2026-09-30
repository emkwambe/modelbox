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

**Every declared constraint is honoured, or the row is not emitted** (Sprint 9
Step 2b, measured on the four imported certified fixtures). Primary keys and
UNIQUE constraints, composite ones included, are distinct; foreign keys repeat
a parent row, including a row of the same table, and are NULL where no parent
can exist yet (a nullable key closing a cycle); CHECK constraints are read on
their syntax tree, values are drawn within the ranges and value lists they
state, and every row is evaluated against every CHECK before it is kept. With
a ``source_dialect`` each column is generated for its type in the target, as
the DDL export writes it, and a generated (computed) column is never written.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import logging
import re
import string
import zlib
from dataclasses import dataclass, field
from random import Random
from typing import Any

import networkx as nx
import sqlglot
from sqlglot import exp

from app.schemas.data_model import ColumnSchema, EntitySchema, SynthesizedModel
from app.services.graph_engine import GraphEngine

logger = logging.getLogger(__name__)

_FIRST = ["Ava", "Noah", "Mia", "Liam", "Ivy", "Ezra", "Zoe", "Kai", "Nora", "Leo"]
_LAST = ["Kim", "Ono", "Diaz", "Bauer", "Cruz", "Frost", "Vance", "Reyes", "Sato", "Ali"]
_CITIES = ["Nairobi", "Lagos", "Cairo", "Accra", "Dar es Salaam", "Kigali", "Tunis"]
_COUNTRIES = ["Kenya", "Nigeria", "Egypt", "Ghana", "Tanzania", "Rwanda", "Tunisia"]
_STREETS = ["Baobab Ave", "Acacia Rd", "Nile St", "Savanna Way", "Harbor Blvd"]

# A CHECK that reads the current date (SQL Server's GETDATE()) is evaluated at
# this fixed date, so the output stays deterministic. It is in the past, so an
# upper bound computed from it is stricter than the one the database applies.
_REFERENCE_DATE = datetime.date(2024, 1, 1)
# Attempts at a row before it is given up. A row that cannot satisfy its
# constraints is left out rather than emitted to be refused.
_ATTEMPTS = 40
_SMALLINT_MAX = 32_767
_NUMERIC_CEILING = 1_000_000.0


@dataclass
class SeedResult:
    """A generated seed dataset."""

    files: dict[str, str] = field(default_factory=dict)
    generation_order: list[str] = field(default_factory=list)
    # Rows given up per entity: no values could satisfy every constraint.
    rows_skipped: dict[str, int] = field(default_factory=dict)


@dataclass
class _Domain:
    """What a column's CHECK constraints allow: a list of values, or bounds."""

    values: list[object] | None = None
    low: object | None = None
    low_strict: bool = False
    high: object | None = None
    high_strict: bool = False


@dataclass
class _Rules:
    """An entity's constraints, read once."""

    columns: list[ColumnSchema]  # the columns written, with their target types
    keys: list[list[str]]  # the primary key and every UNIQUE constraint
    checks: list[exp.Expression]
    domains: dict[str, _Domain]
    orderings: list[tuple[str, str, bool]]  # (later, earlier, strict)


class SyntheticSeedGenerator:
    """Generates FK-consistent synthetic rows for a model graph."""

    def __init__(self, dialect: str = "postgres", seed: int = 1337, source_dialect: str | None = None) -> None:
        self._dialect = dialect
        self._seed = seed
        # The dialect the model's types and CHECKs are written in. When given,
        # each column is generated for its type in `dialect` (Step 2b).
        self._source = source_dialect

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(
        self, model: SynthesizedModel, row_count: int, fmt: str = "sql_insert"
    ) -> SeedResult:
        order = self._generation_order(model)
        by_name = {e.entity_name: e for e in model.entities}
        rules = {e.entity_name: self._rules(e) for e in model.entities}

        # Resolved relationships by child entity. A composite foreign key is
        # one relationship, so a child row copies all its referenced columns
        # from one parent row: columns drawn independently could combine into
        # a key no parent has.
        foreign_keys: dict[str, list[tuple[list[str], str, list[str]]]] = {}
        for rel in model.relationships:
            if rel.resolved:
                foreign_keys.setdefault(rel.from_ref, []).append(
                    (rel.from_columns, rel.to_ref, rel.to_columns))

        rows_by_entity: dict[str, list[dict[str, object]]] = {}
        skipped: dict[str, int] = {}
        for ename in order:
            entity = by_name.get(ename)
            if entity is None:
                continue
            rows = self._entity_rows(entity, rules[ename], foreign_keys.get(ename, []), rows_by_entity, row_count)
            rows_by_entity[ename] = rows
            if len(rows) < row_count:
                skipped[ename] = row_count - len(rows)
                logger.warning("Seed: %d of %d rows of %s could not satisfy their constraints and were left out.",
                               row_count - len(rows), row_count, ename)

        present_order = [e for e in order if e in rows_by_entity]
        written = {name: [c.name for c in rule.columns] for name, rule in rules.items()}
        if fmt == "csv":
            files = self._render_csv(written, rows_by_entity, present_order)
        else:
            files = self._render_sql(written, rows_by_entity, present_order)
        return SeedResult(files=files, generation_order=present_order, rows_skipped=skipped)

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------
    def _entity_rows(self, entity: EntitySchema, rules: _Rules,
                     foreign_keys: list[tuple[list[str], str, list[str]]],
                     rows_by_entity: dict[str, list[dict[str, object]]],
                     row_count: int) -> list[dict[str, object]]:
        ename = entity.entity_name
        rows: list[dict[str, object]] = []
        seen: list[set[tuple[object, ...]]] = [set() for _ in rules.keys]
        written = {c.name for c in rules.columns}
        nullable = {c.name for c in rules.columns if c.is_nullable and not c.is_primary_key}
        key_columns = {c for key in rules.keys for c in key}
        for i in range(row_count):
            for attempt in range(_ATTEMPTS):
                row = self._candidate(entity, rules, foreign_keys, rows_by_entity, rows, written, nullable,
                                      key_columns, i, attempt)
                if row is None:
                    continue
                keys = [tuple(row.get(c) for c in key) for key in rules.keys]
                if any(None not in key and key in taken for key, taken in zip(keys, seen, strict=True)):
                    continue
                if any(_evaluate(check, row) is False for check in rules.checks):
                    continue
                for key, taken in zip(keys, seen, strict=True):
                    taken.add(key)
                rows.append(row)
                break
            else:
                logger.debug("Seed: gave up row %d of %s", i, ename)
        return rows

    def _candidate(self, entity: EntitySchema, rules: _Rules,
                   foreign_keys: list[tuple[list[str], str, list[str]]],
                   rows_by_entity: dict[str, list[dict[str, object]]],
                   rows: list[dict[str, object]], written: set[str], nullable: set[str],
                   key_columns: set[str], i: int, attempt: int) -> dict[str, object] | None:
        """One row, or None where a foreign key that cannot be NULL has no parent."""
        ename = entity.entity_name
        row: dict[str, object] = {}
        for from_columns, parent, to_columns in foreign_keys:
            if not set(from_columns) <= written:
                continue
            # A self-reference repeats a row already made; a parent not yet
            # made (a key closing a cycle) has none.
            parents = rows if parent == ename else rows_by_entity.get(parent, [])
            if not parents:
                if set(from_columns) <= nullable:
                    for child_column in from_columns:
                        row.setdefault(child_column, None)
                    continue
                return None
            # A key that is also a primary or unique key walks the parents in
            # a fixed shuffled order, so successive rows take distinct ones.
            rng = self._rng(ename, ",".join(from_columns), i, attempt)
            if set(from_columns) & key_columns:
                order = list(range(len(parents)))
                Random(self._seed ^ zlib.crc32(f"{ename}|{from_columns}".encode())).shuffle(order)
                chosen = parents[order[(i + attempt) % len(parents)]]
            else:
                chosen = rng.choice(parents)
            if parent == ename and attempt > _ATTEMPTS // 2 and set(from_columns) <= nullable:
                chosen = {c: None for c in to_columns}
            # A foreign key must repeat a parent's values, so it is exempt from
            # the distinctness below: referential integrity outranks UNIQUE.
            for child_column, parent_column in zip(from_columns, to_columns, strict=True):
                row.setdefault(child_column, chosen.get(parent_column))
        for col in rules.columns:
            if col.name in row:
                continue
            rng = self._rng(ename, col.name, i, attempt)
            domain = rules.domains.get(col.name)
            # Later attempts try NULL for a nullable column a CHECK names: SQL
            # accepts a CHECK that is unknown, and most CHECKs allow NULL.
            if attempt >= 3 and col.name in nullable and domain is not None and rng.random() < 0.5:
                row[col.name] = None
                continue
            if col.is_primary_key and domain is None:
                # Distinct by row; a retry is for the other columns.
                value = self._fit(self._pk_value(entity, col, i), col)
            elif col.name in key_columns and domain is None and attempt > 0:
                # A UNIQUE value that collided: a heuristic can repeat itself
                # (a long name truncated to CHAR(2)), a key-style value cannot.
                value = self._fit(self._pk_value(entity, col, i + (attempt - 1) * 10_007), col)
            else:
                value = self._fit(self._value(entity, col, i, rng, domain), col)
            row[col.name] = value
        for later, earlier, strict in rules.orderings:
            if row.get(later) is None or row.get(earlier) is None:
                continue
            sign = _compare(row[later], row[earlier])
            if sign is not None and not (sign > 0 or (not strict and sign == 0)):
                row[later] = _after(row[earlier], strict)
        return row

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _rules(self, entity: EntitySchema) -> _Rules:
        columns = self._typed_columns(entity)
        names = [c.name for c in columns]
        keys = ([entity.primary_key] if entity.primary_key else []) + [u.columns for u in entity.unique_constraints]
        keys = [k for k in keys if set(k) <= set(names)]
        dialect = self._source or "snowflake"
        checks: list[exp.Expression] = []
        for check in entity.check_constraints:
            try:
                parsed = sqlglot.parse_one(f"SELECT 1 WHERE {check.expression}", read=dialect)
            except sqlglot.errors.SqlglotError:
                logger.warning("Seed: CHECK %r on %s does not parse; not enforced", check.expression, entity.entity_name)
                continue
            where = parsed.args.get("where") if isinstance(parsed, exp.Select) else None
            if where is not None:
                checks.append(where.this)
        domains: dict[str, _Domain] = {}
        orderings: list[tuple[str, str, bool]] = []
        for tree in checks:
            _read_check(tree, names, domains, orderings)
        return _Rules(columns=columns, keys=keys, checks=checks, domains=domains, orderings=orderings)

    def _typed_columns(self, entity: EntitySchema) -> list[ColumnSchema]:
        """The columns a row is written with, each with its type in the target.

        A generated column is never written: the database computes it and
        refuses a value. Without a source dialect the declared types are used.
        """
        if self._source is None:
            return [c for c in entity.columns if c.data_type != "COMPUTED"]
        from app.services.ddl_export import DdlExportError, column_type

        out = []
        for column in entity.columns:
            if column.data_type == "COMPUTED":
                continue
            try:
                written = column_type(column, entity, self._source, self._dialect)
            except DdlExportError:
                # The DDL export refuses this type, so there is no table to
                # load; the declared type still yields a plausible value.
                written = column.data_type
            if written is not None:
                out.append(column.model_copy(update={"data_type": written}))
        return out

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------
    def _generation_order(self, model: SynthesizedModel) -> list[str]:
        """Parents first. A cycle is broken at a foreign key that may be NULL,
        which is then NULL until its parent exists; a self-reference needs no
        break, since a row can reference one made before it."""
        graph = GraphEngine.build_graph(model.entities, model.relationships)
        graph.remove_edges_from(list(nx.selfloop_edges(graph)))
        # An edge runs child -> parent and stands for every relationship between
        # the two, so it can be broken only if all of them may be NULL.
        edges: dict[tuple[str, str], bool] = {}
        for rel in model.relationships:
            if rel.resolved:
                key = (rel.from_ref, rel.to_ref)
                edges[key] = edges.get(key, True) and _all_nullable(model, rel.from_ref, rel.from_columns)
        nullable = {key for key, may_be_null in edges.items() if may_be_null}
        for _ in range(len(model.relationships) + 1):
            try:
                return GraphEngine.topological_order(graph)
            except nx.NetworkXUnfeasible:
                cycle = nx.find_cycle(graph)
                breakable = [(u, v) for u, v, *_ in cycle if (u, v) in nullable]
                graph.remove_edge(*(breakable[0] if breakable else cycle[0][:2]))
        # Cyclic FKs with nothing to break: fall back to declared order.
        return [e.entity_name for e in model.entities]

    # ------------------------------------------------------------------
    # Value generation
    # ------------------------------------------------------------------
    def _rng(self, entity: str, col: str, i: int, attempt: int = 0) -> Random:
        salt = zlib.crc32(f"{entity}|{col}|{i}".encode() + (f"|{attempt}".encode() if attempt else b"")) & 0xFFFFFFFF
        return Random(self._seed ^ salt)

    def _pk_value(self, entity: EntitySchema, col: ColumnSchema, i: int) -> object:
        t = col.data_type.upper()
        if "UUID" in t or "UNIQUEIDENTIFIER" in t:
            r = self._rng(entity.entity_name, col.name, i)
            # Drawn in the same order as before, so seeded values are unchanged.
            a, b, c = r.getrandbits(32), r.getrandbits(16), r.getrandbits(12)
            d, e = r.getrandbits(16), r.getrandbits(48)
            return f"{a:08x}-{b:04x}-4{c:03x}-{d:04x}-{e:012x}"
        if self._is_int(t) or self._is_whole_number(t):
            return i + 1
        if any(tok in t for tok in ("TIMESTAMP", "DATETIME")):
            return f"{(datetime.date(2020, 1, 1) + datetime.timedelta(days=i)).isoformat()} 00:00:00"
        if "DATE" in t:
            return (datetime.date(2020, 1, 1) + datetime.timedelta(days=i)).isoformat()
        length = self._declared_length(t)
        if length is not None and length < len(f"{entity.entity_name}_{i + 1}"):
            return self._counter(i + 1, length)
        return f"{entity.entity_name}_{i + 1}"

    def _value(self, entity: EntitySchema, col: ColumnSchema, i: int, rng: Random | None = None,
               domain: _Domain | None = None) -> object:
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

        The same violation was later found in the dbt exporter (H11), so the
        rule is stated once for the whole product in
        ``app/services/exporter_service`` rather than twice as a local note.
        """
        name = col.name.lower()
        t = col.data_type.upper()
        rng = rng or self._rng(entity.entity_name, col.name, i)

        def pick(seq: list[str]) -> str:
            return seq[rng.randrange(len(seq))]

        # -- declared constraints, in order of how tightly they bind ---------
        if domain is not None and domain.values:
            choices = [v for v in domain.values if v is not None] or domain.values
            return choices[rng.randrange(len(choices))]
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

        temporal = self._temporal(t)
        if temporal is not None:
            return self._temporal_value(temporal, rng, domain)

        numeric = self._numeric_value(col, rng, domain)
        if numeric is not None:
            return numeric

        # -- values of a type, where the type admits only its own ------------
        if "BOOL" in t:
            return rng.random() < 0.5
        if "UUID" in t or "UNIQUEIDENTIFIER" in t:
            return self._pk_value(entity, col, i + rng.randrange(1_000_000))
        if t.endswith("[]"):
            return "{" + f'"{col.name}_{i + 1}"' + "}"
        if t.startswith("JSON"):
            return "{}"
        if t.startswith("XML"):
            return f"<{re.sub(r'[^A-Za-z0-9_]', '_', col.name) or 'v'}/>"
        if self._is_int(t):
            high = _SMALLINT_MAX if "SMALLINT" in t or "TINYINT" in t else 100000
            return rng.randint(1, high)

        # -- name-driven heuristics, for character columns --------------------
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

    def _numeric_value(self, col: ColumnSchema, rng: Random, domain: _Domain | None = None) -> float | int | None:
        """A number honouring declared bounds *and* declared precision/scale.

        These are three independent constraints, and a value can satisfy one
        while violating another: ``6332.15`` is inside no declared range, has
        six significant digits against a declared five, and only the scale
        happens to be right. Fixing the range alone would leave a value that
        still cannot be inserted. A CHECK's bounds (``Rate >= 6.50 AND Rate <=
        200.00``) are a fourth, and bind as tightly as declared ones.
        """
        upper = col.data_type.upper()
        is_decimal = any(
            tok in upper for tok in ("NUMERIC", "DECIMAL", "NUMBER", "FLOAT",
                                     "DOUBLE", "REAL", "MONEY")
        )
        is_integer = self._is_int(upper)
        if not (is_decimal or is_integer):
            return None
        bounded = domain is not None and (domain.low is not None or domain.high is not None)
        if col.min_value is None and col.max_value is None and not is_decimal and not bounded:
            return None  # unconstrained integers keep their existing behaviour

        precision, scale = self._precision_scale(col.data_type)
        if is_integer:
            scale = 0
        step = 10.0 ** -(scale if scale is not None else 2)
        low = col.min_value if col.min_value is not None else 0.0
        high = col.max_value if col.max_value is not None else None
        if high is None:
            # The widest value the declared precision admits, so a bare
            # NUMERIC(5,2) never produces six digits.
            # `_precision_scale` returns a scale whenever it returns a precision.
            high = (
                float(10 ** (precision - scale)) - (10.0 ** -scale)
                if precision is not None and scale is not None
                else (float(_SMALLINT_MAX) if "SMALLINT" in upper or "TINYINT" in upper else 10_000.0)
            )
            # Near 10^15 a float cannot hold four decimal places, so rounding
            # can land on the bound itself: MONEY is NUMERIC(19,4). No sample
            # value needs to be that large.
            high = min(high, _NUMERIC_CEILING)
        if domain is not None:
            if isinstance(domain.low, (int, float)):
                low = max(low, float(domain.low) + (step if domain.low_strict else 0.0))
            if isinstance(domain.high, (int, float)):
                high = min(high, float(domain.high) - (step if domain.high_strict else 0.0))
        # Contradictory bounds are a lint finding about the model, not ours.
        low = min(low, high)

        if is_integer or scale == 0:
            return rng.randint(int(-(-low // 1)), max(int(-(-low // 1)), int(high // 1)))
        value = rng.uniform(low, high)
        return round(value, scale if scale is not None else 2)

    @staticmethod
    def _temporal(t: str) -> str | None:
        """'timestamp', 'date' or 'time' for a temporal type, else None."""
        if any(tok in t for tok in ("TIMESTAMP", "DATETIME", "SMALLDATETIME")):
            return "timestamp"
        if "DATE" in t:
            return "date"
        if re.match(r"TIME\b", t):
            return "time"
        return None

    def _temporal_value(self, kind: str, rng: Random, domain: _Domain | None) -> str:
        if kind == "time":
            return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        low, high = datetime.date(2020, 1, 1), datetime.date(2023, 12, 28)
        bound_low = _date(domain.low) if domain is not None and isinstance(domain.low, str) else None
        bound_high = _date(domain.high) if domain is not None and isinstance(domain.high, str) else None
        if domain is not None and bound_low is not None:
            bound_low += datetime.timedelta(days=1 if domain.low_strict else 0)
        if domain is not None and bound_high is not None:
            bound_high -= datetime.timedelta(days=1 if domain.high_strict else 0)
        low = max(low, bound_low) if bound_low else low
        high = min(high, bound_high) if bound_high else high
        if low > high:
            # The default window misses the bounds: draw within them instead,
            # or within ten years of the one bound there is.
            low = bound_low or high - datetime.timedelta(days=3650)
            high = bound_high or low + datetime.timedelta(days=3650)
        span = max(0, (high - low).days)
        day = low + datetime.timedelta(days=rng.randint(0, span))
        if kind == "date":
            return day.isoformat()
        return f"{day.isoformat()} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"

    @staticmethod
    def _precision_scale(data_type: str) -> tuple[int | None, int | None]:
        match = re.search(r"\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)", data_type)
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2) or 0)

    @staticmethod
    def _declared_length(data_type: str) -> int | None:
        match = re.search(r"(?:N?VAR)?N?CHAR2?\s*\(\s*(\d+)(?:\s+(?:BYTE|CHAR))?\s*\)", data_type, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _is_int(t: str) -> bool:
        return any(tok in t for tok in ("INT", "SERIAL")) and "POINT" not in t and "INTERVAL" not in t

    @classmethod
    def _is_whole_number(cls, t: str) -> bool:
        """NUMERIC(p, 0), and NUMERIC with no scale, which Oracle's surrogate
        keys are declared as (a bare NUMBER): each holds a whole number."""
        precision, scale = cls._precision_scale(t)
        return any(tok in t for tok in ("NUMERIC", "DECIMAL", "NUMBER")) and (precision is None or scale == 0)

    @staticmethod
    def _counter(n: int, width: int) -> str:
        """``n`` in base 36, at most ``width`` characters: a distinct short code."""
        digits = string.digits + string.ascii_uppercase
        out = ""
        while n:
            n, r = divmod(n, 36)
            out = digits[r] + out
        return (out or "0")[-width:]

    @staticmethod
    def _date(rng: Random) -> str:
        return f"{rng.randint(2020, 2024)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"

    def _timestamp(self, rng: Random) -> str:
        return (
            f"{self._date(rng)} "
            f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        )

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
        columns: dict[str, list[str]],
        rows_by_entity: dict[str, list[dict[str, object]]],
        order: list[str],
    ) -> dict[str, str]:
        from app.services.ddl_export import quote

        chunks = [
            "-- Synthetic seed data generated by ModelBox AI (FR-2.4).",
            f"-- Generation order (FK-safe): {', '.join(order)}",
            "",
        ]
        for ename in order:
            cols = columns[ename]
            rows = rows_by_entity[ename]
            if not rows:
                continue
            values = [
                "  (" + ", ".join(self._sql_literal(row.get(c)) for c in cols) + ")"
                for row in rows
            ]
            # Named as the DDL export names them, so a mixed-case table resolves.
            chunks.append(
                f"INSERT INTO {quote(ename)} ({', '.join(quote(c) for c in cols)}) VALUES\n"
                + ",\n".join(values)
                + ";\n"
            )
        return {f"seed_{self._dialect}.sql": "\n".join(chunks)}

    def _render_csv(
        self,
        columns: dict[str, list[str]],
        rows_by_entity: dict[str, list[dict[str, object]]],
        order: list[str],
    ) -> dict[str, str]:
        files: dict[str, str] = {}
        for ename in order:
            cols = columns[ename]
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            writer.writerow(cols)
            for row in rows_by_entity[ename]:
                writer.writerow([self._csv_cell(row.get(c)) for c in cols])
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


def _all_nullable(model: SynthesizedModel, entity_name: str, columns: list[str]) -> bool:
    entity = next((e for e in model.entities if e.entity_name == entity_name), None)
    if entity is None:
        return False
    by_name = {c.name: c for c in entity.columns}
    return all(c in by_name and by_name[c].is_nullable and not by_name[c].is_primary_key for c in columns)


# ----------------------------------------------------------------------
# CHECK constraints, read on their syntax tree
# ----------------------------------------------------------------------

def _unwrap(node: exp.Expression) -> exp.Expression:
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _column_name(node: exp.Expression, names: list[str]) -> tuple[str, bool] | None:
    """(the entity's column a node reads, whether through UPPER()), or None."""
    node = _unwrap(node)
    folded = False
    if isinstance(node, (exp.Upper, exp.Lower)):
        folded, node = True, _unwrap(node.this)
    if isinstance(node, exp.Column):
        exact = {n: n for n in names}
        found = exact.get(node.name) or {n.lower(): n for n in names}.get(node.name.lower())
        return (found, folded) if found else None
    return None


def _literal(node: exp.Expression) -> object:
    """A constant's value: a number, a string, an ISO date, or ``_UNKNOWN``."""
    node = _unwrap(node)
    if isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.National):
        return node.name
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.name
        return float(node.name) if "." in node.name or "e" in node.name.lower() else int(node.name)
    if isinstance(node, exp.Neg):
        inner = _literal(node.this)
        return -inner if isinstance(inner, (int, float)) else _UNKNOWN
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, (exp.CurrentTimestamp, exp.CurrentDate)) or (
            isinstance(node, exp.Anonymous) and node.name.upper() in ("GETDATE", "SYSDATE", "NOW")):
        return _REFERENCE_DATE.isoformat()
    if isinstance(node, (exp.DateAdd, exp.TsOrDsAdd)):
        base = _literal(node.this)
        amount = _literal(node.expression)
        unit = str(node.args.get("unit") or "DAY").upper().strip("'")
        day = _date(base) if isinstance(base, str) else None
        if day is not None and isinstance(amount, (int, float)):
            n = int(amount)
            if "YEAR" in unit:
                return day.replace(year=day.year + n).isoformat()
            if "MONTH" in unit:
                month = day.month - 1 + n
                return day.replace(year=day.year + month // 12, month=month % 12 + 1).isoformat()
            return (day + datetime.timedelta(days=n)).isoformat()
    return _UNKNOWN


class _Unknown:
    def __repr__(self) -> str:
        return "UNKNOWN"


_UNKNOWN: Any = _Unknown()


def _date(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _read_check(node: exp.Expression, names: list[str], domains: dict[str, _Domain],
                orderings: list[tuple[str, str, bool]]) -> None:
    """The value lists, bounds and orderings a CHECK states, for generation.

    Only what it states unambiguously: a conjunction's parts, a disjunction of
    equalities (and IS NULL) on one column, and one column compared with a
    constant or with another column. Anything else is left to the evaluator,
    which checks every row against the whole expression.
    """
    node = _unwrap(node)
    if isinstance(node, exp.And):
        _read_check(node.this, names, domains, orderings)
        _read_check(node.expression, names, domains, orderings)
        return
    if isinstance(node, exp.Or):
        found = _choices(node, names)
        if found is not None and found[1]:
            domains.setdefault(found[0], _Domain()).values = found[1]
            return
        # An ordering with IS NULL escapes: a >= b OR a IS NULL.
        for branch in _branches(node):
            _read_ordering(_unwrap(branch), names, orderings)
        return
    found = _choices(node, names)
    if found is not None:
        domains.setdefault(found[0], _Domain()).values = found[1]
        return
    if _read_ordering(node, names, orderings):
        return
    if isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE)):
        left, right = _column_name(node.this, names), _column_name(node.expression, names)
        op: type[exp.Binary] = type(node)
        if left is not None and right is None:
            value = _literal(node.expression)
        elif right is not None and left is None:
            left, value = right, _literal(node.this)
            op = {exp.GT: exp.LT, exp.GTE: exp.LTE, exp.LT: exp.GT, exp.LTE: exp.GTE}[op]
        else:
            return
        if value is _UNKNOWN or value is None or left[1]:
            return
        domain = domains.setdefault(left[0], _Domain())
        if op in (exp.GT, exp.GTE):
            domain.low, domain.low_strict = value, op is exp.GT
        else:
            domain.high, domain.high_strict = value, op is exp.LT


def _branches(node: exp.Expression) -> list[exp.Expression]:
    node = _unwrap(node)
    if isinstance(node, exp.Or):
        return _branches(node.this) + _branches(node.expression)
    return [node]


def _choices(node: exp.Expression, names: list[str]) -> tuple[str, list[object]] | None:
    """(column, the values it may take) for ``col = v``, ``UPPER(col) = 'V'``,
    ``col IN (…)``, ``col IS NULL``, ``col LIKE 'pattern'`` or an OR of these."""
    node = _unwrap(node)
    if isinstance(node, exp.Or):
        owner: str | None = None
        exact: list[object] = []
        patterned: list[object] = []
        for branch in _branches(node):
            found = _choices(branch, names)
            if found is None or (owner is not None and found[0] != owner):
                return None
            owner = found[0]
            (patterned if isinstance(branch, exp.Like) else exact).extend(found[1])
        # An equality means the same in every dialect; a LIKE pattern may not
        # (T-SQL's [A-Z] is a character class, PostgreSQL's is literal text).
        return (owner, exact or patterned) if owner is not None else None
    if isinstance(node, exp.EQ):
        for side, other in ((node.this, node.expression), (node.expression, node.this)):
            column = _column_name(side, names)
            value = _literal(other)
            if column is not None and value is not _UNKNOWN:
                return column[0], [value]
        return None
    if isinstance(node, exp.In):
        column = _column_name(node.this, names)
        values = [_literal(v) for v in node.expressions]
        if column is not None and all(v is not _UNKNOWN for v in values):
            return column[0], values
        return None
    if isinstance(node, exp.Is) and isinstance(_unwrap(node.expression), exp.Null):
        column = _column_name(node.this, names)
        return (column[0], [None]) if column is not None else None
    if isinstance(node, exp.Is) and isinstance(_unwrap(node.expression), exp.JSON):
        column = _column_name(node.this, names)
        return (column[0], ["{}"]) if column is not None else None
    if isinstance(node, exp.Like):
        column = _column_name(node.this, names)
        pattern = _literal(node.expression)
        if column is not None and isinstance(pattern, str):
            sample = _like_sample(pattern)
            return (column[0], [sample]) if sample is not None else None
    return None


def _read_ordering(node: exp.Expression, names: list[str], orderings: list[tuple[str, str, bool]]) -> bool:
    """``later >= earlier`` between two columns of the entity."""
    if not isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE)):
        return False
    left, right = _column_name(node.this, names), _column_name(node.expression, names)
    if left is None or right is None or left[1] or right[1]:
        return False
    if isinstance(node, (exp.GT, exp.GTE)):
        orderings.append((left[0], right[0], isinstance(node, exp.GT)))
    else:
        orderings.append((right[0], left[0], isinstance(node, exp.LT)))
    return True


def _like_sample(pattern: str) -> str | None:
    """A string matching a LIKE pattern (T-SQL character classes included)."""
    out, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "[":
            end = pattern.find("]", i)
            if end == -1:
                return None
            body = pattern[i + 1:end].lstrip("^")
            out += body[0] if body else "A"
            i = end + 1
            continue
        out += {"%": "", "_": "x"}.get(ch, ch)
        i += 1
    return out


def _like(value: str, pattern: str) -> bool:
    regex = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "[":
            end = pattern.find("]", i)
            if end != -1:
                body = pattern[i + 1:end]
                regex += "[" + ("^" + re.escape(body[1:]) if body.startswith("^") else body) + "]"
                i = end + 1
                continue
        regex += ".*" if ch == "%" else "." if ch == "_" else re.escape(ch)
        i += 1
    return re.fullmatch(regex, value, re.DOTALL) is not None


def _compare(a: object, b: object) -> int | None:
    """-1, 0 or 1; None when the two cannot be compared."""
    if isinstance(a, bool) and isinstance(b, bool):
        return (a > b) - (a < b)
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)  # ISO dates and times compare as text
    if isinstance(a, (int, float)) and isinstance(b, str) or isinstance(a, str) and isinstance(b, (int, float)):
        try:
            x, y = float(str(a)), float(str(b))
        except ValueError:
            return None
        return (x > y) - (x < y)
    return None


def _after(value: object, strict: bool) -> object:
    """A value not before ``value`` (after it, if ``strict``)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value + 1 if strict else value
    if isinstance(value, str) and (day := _date(value)) is not None:
        later = day + datetime.timedelta(days=1 if strict else 0)
        return later.isoformat() + value[10:]
    return value


def _evaluate(node: exp.Expression, row: dict[str, object]) -> bool | None:
    """A CHECK's truth for a row, in SQL's three values (None is unknown).

    A CHECK is satisfied unless it is False. An expression this evaluator does
    not understand is unknown too, and the database then has the last word.
    """
    node = _unwrap(node)
    if isinstance(node, exp.And):
        a, b = _evaluate(node.this, row), _evaluate(node.expression, row)
        return False if a is False or b is False else (None if a is None or b is None else True)
    if isinstance(node, exp.Or):
        a, b = _evaluate(node.this, row), _evaluate(node.expression, row)
        return True if a is True or b is True else (None if a is None or b is None else False)
    if isinstance(node, exp.Not):
        inner = _evaluate(node.this, row)
        return None if inner is None else not inner
    if isinstance(node, exp.Is):
        value = _value_of(node.this, row)
        target = _unwrap(node.expression)
        if value is _UNKNOWN:
            return None
        if isinstance(target, exp.Null):
            return value is None
        if isinstance(target, exp.JSON):
            if value is None:
                return None
            try:
                json.loads(str(value))
            except ValueError:
                return False
            return True
        return None
    if isinstance(node, exp.In):
        value = _value_of(node.this, row)
        options = [_value_of(v, row) for v in node.expressions]
        if value is None or value is _UNKNOWN or any(o is _UNKNOWN for o in options):
            return None
        return any(_compare(value, o) == 0 for o in options)
    if isinstance(node, exp.Like):
        value, pattern = _value_of(node.this, row), _value_of(node.expression, row)
        if not isinstance(value, str) or not isinstance(pattern, str):
            return None
        return _like(value, pattern)
    comparisons = {exp.EQ: lambda c: c == 0, exp.NEQ: lambda c: c != 0, exp.GT: lambda c: c > 0,
                   exp.GTE: lambda c: c >= 0, exp.LT: lambda c: c < 0, exp.LTE: lambda c: c <= 0}
    for kind, test in comparisons.items():
        if isinstance(node, kind):
            left, right = _value_of(node.this, row), _value_of(node.expression, row)
            if left is None or right is None or left is _UNKNOWN or right is _UNKNOWN:
                return None
            outcome = _compare(left, right)
            return None if outcome is None else test(outcome)
    return None


def _value_of(node: exp.Expression, row: dict[str, object]) -> object:
    node = _unwrap(node)
    if isinstance(node, (exp.Upper, exp.Lower)):
        inner = _value_of(node.this, row)
        if isinstance(inner, str):
            return inner.upper() if isinstance(node, exp.Upper) else inner.lower()
        return inner
    if isinstance(node, exp.Column):
        if node.name in row:
            return row[node.name]
        folded = {k.lower(): v for k, v in row.items()}
        return folded.get(node.name.lower(), _UNKNOWN)
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
        a, b = _value_of(node.this, row), _value_of(node.expression, row)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return _UNKNOWN if a is not None and b is not None else None
        if isinstance(node, exp.Add):
            return a + b
        if isinstance(node, exp.Sub):
            return a - b
        if isinstance(node, exp.Mul):
            return a * b
        return a / b if b else _UNKNOWN
    return _literal(node)
