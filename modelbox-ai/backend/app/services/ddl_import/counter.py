"""Count what a DDL file declares, independently of the importer.

Reconciliation compares these counts with what the import produced, so they
must not share the importer's failure modes. This module therefore imports
nothing from sqlglot, the splitter or the normalizer (a structural test holds
that): it masks strings, comments and procedural bodies with its own small
lexer, then reads ``CREATE TABLE``, ``ALTER TABLE … ADD``, ``ATTACH
PARTITION`` / ``PARTITION OF`` and ``COMMENT ON`` with regular expressions.
A statement the importer silently dropped is still counted here, and the
difference is the gap.

What is counted, per table and in total, with partitions kept apart from
tables: columns, primary keys, foreign keys, UNIQUE constraints, CHECK
constraints (a NOT NULL is not a CHECK), and table and column descriptions.
Indexes, including unique indexes, are not constraints and are not counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("columns", "primary_keys", "foreign_keys", "unique_constraints",
         "check_constraints", "table_descriptions", "column_descriptions")

_ORACLE_BLOCK = re.compile(
    r"^[ \t]*(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:PROCEDURE|FUNCTION|PACKAGE|TRIGGER|TYPE\s+BODY)\b|DECLARE\b|BEGIN\b)"
    r".*?^[ \t]*/[ \t]*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_DOLLAR = re.compile(r"\$([A-Za-z_][A-Za-z_0-9]*)?\$")
_NAME = r"((?:\"[^\"]+\"|[\w$#]+)(?:\s*\.\s*(?:\"[^\"]+\"|[\w$#]+))*)"
_CREATE_TABLE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:(?:GLOBAL|LOCAL|TEMP|TEMPORARY|UNLOGGED|HYBRID|TRANSIENT|VOLATILE)\s+)*"
    rf"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_NAME}",
    re.IGNORECASE,
)
_PARTITION_OF = re.compile(rf"^\s*PARTITION\s+OF\s+{_NAME}", re.IGNORECASE)
_ALTER_TABLE = re.compile(rf"\bALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?{_NAME}", re.IGNORECASE)
_ATTACH = re.compile(rf"\bATTACH\s+PARTITION\s+{_NAME}", re.IGNORECASE)
_COMMENT = re.compile(rf"\bCOMMENT\s+ON\s+(TABLE|COLUMN)\s+{_NAME}\s+IS\s+", re.IGNORECASE)
_CONSTRAINT_ITEM = re.compile(
    r"^(?:CONSTRAINT\b|PRIMARY\s+KEY\b|FOREIGN\s+KEY\b|UNIQUE\b|CHECK\b|EXCLUDE\b|LIKE\b|PERIOD\b|SUPPLEMENTAL\b)",
    re.IGNORECASE,
)


@dataclass
class TableCounts:
    name: str
    partition_of: str | None = None
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(KINDS, 0))


def _mask(text: str, dialect: str) -> str:
    """Blank out string contents, comments and procedural bodies, keeping positions.

    A string literal keeps its quotes and becomes ``'x…'`` of the same length,
    so a COMMENT ON's text is still seen to be non-empty.
    """
    if dialect == "oracle":
        text = _ORACLE_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if out[k] != "\n":
                    out[k] = "x"
            i = j + 1
        elif ch == '"':
            j = text.find('"', i + 1)
            i = n if j == -1 else j + 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif dialect != "oracle" and ch == "$" and (m := _DOLLAR.match(text, i)):
            j = text.find(m.group(0), m.end())
            j = n if j == -1 else j + len(m.group(0))
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def _bare(name: str) -> str:
    """The object's own name: the last dotted part, without quotes."""
    parts = re.findall(r"\"([^\"]+)\"|([\w$#]+)", name)
    quoted, plain = parts[-1]
    return quoted or plain


def _body(text: str, start: int) -> tuple[str, int] | None:
    """The parenthesised text opening at or after ``start``, and its end."""
    open_at = text.find("(", start)
    if open_at == -1:
        return None
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1: i], i + 1
    return None


def _items(body: str) -> list[str]:
    items, depth, current = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    items.append("".join(current).strip())
    return [item for item in items if item]


def _constraint_kinds(fragment: str) -> dict[str, int]:
    upper = fragment.upper()
    has_fk_keyword = re.search(r"\bFOREIGN\s+KEY\b", upper) is not None
    return {
        "primary_keys": len(re.findall(r"\bPRIMARY\s+KEY\b", upper)),
        "foreign_keys": len(re.findall(r"\bFOREIGN\s+KEY\b", upper))
        or (0 if has_fk_keyword else len(re.findall(r"\bREFERENCES\b", upper))),
        "unique_constraints": len(re.findall(r"\bUNIQUE\b", upper)),
        "check_constraints": len(re.findall(r"\bCHECK\s*\(", upper)),
    }


def count(text: str, dialect: str) -> dict[str, TableCounts]:
    """Per-table counts, keyed by bare table name; partitions carry their parent."""
    masked = _mask(text, dialect)
    tables: dict[str, TableCounts] = {}

    for match in _CREATE_TABLE.finditer(masked):
        name = _bare(match.group(1))
        table = tables.setdefault(name, TableCounts(name))
        after = masked[match.end():]
        if (partition := _PARTITION_OF.match(after)) is not None:
            table.partition_of = _bare(partition.group(1))
        found = _body(masked, match.end())
        if found is None:
            continue
        for item in _items(found[0]):
            if _CONSTRAINT_ITEM.match(item):
                kinds = _constraint_kinds(item)
            else:
                table.counts["columns"] += 1
                kinds = _constraint_kinds(re.sub(r"^\S+\s*", "", item, count=1))
            for kind, n in kinds.items():
                table.counts[kind] += n

    for match in _ALTER_TABLE.finditer(masked):
        name = _bare(match.group(1))
        end = masked.find(";", match.end())
        statement = masked[match.end(): len(masked) if end == -1 else end]
        if (attach := _ATTACH.search(statement)) is not None:
            child = tables.setdefault(_bare(attach.group(1)), TableCounts(_bare(attach.group(1))))
            child.partition_of = name
            continue
        if re.search(r"\bADD\b", statement, re.IGNORECASE) is None:
            continue
        table = tables.setdefault(name, TableCounts(name))
        for kind, n in _constraint_kinds(statement).items():
            table.counts[kind] += n

    for match in _COMMENT.finditer(masked):
        # The masked literal is x's, with any newlines the text had kept.
        literal = re.match(r"'([x\n]*)'", masked[match.end():])
        if literal is None or "x" not in literal.group(1):
            continue  # COMMENT ON … IS '' or IS NULL removes a description
        target = match.group(2)
        parts = re.findall(r"\"([^\"]+)\"|([\w$#]+)", target)
        names = [q or p for q, p in parts]
        table_name = names[-1] if match.group(1).upper() == "TABLE" else names[-2]
        table = tables.setdefault(table_name, TableCounts(table_name))
        key = "table_descriptions" if match.group(1).upper() == "TABLE" else "column_descriptions"
        table.counts[key] += 1
    return tables


def totals(tables: dict[str, TableCounts]) -> dict[str, dict[str, int]]:
    """Totals for tables and for partitions, kept apart."""
    out = {
        "tables": {"count": 0, **dict.fromkeys(KINDS, 0)},
        "partitions": {"count": 0, **dict.fromkeys(KINDS, 0)},
    }
    for table in tables.values():
        bucket = out["partitions" if table.partition_of else "tables"]
        bucket["count"] += 1
        for kind in KINDS:
            bucket[kind] += table.counts[kind]
    return out
