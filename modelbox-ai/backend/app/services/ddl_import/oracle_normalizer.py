"""Strip the physical clauses of Oracle export DDL before it is parsed.

``DBMS_METADATA.GET_DDL`` writes storage, segment and constraint-state clauses
that sqlglot cannot parse (probed clause by clause before Sprint 8):
``NOT NULL ENABLE`` fails,
``STORAGE(...)`` fails, and an ``ALTER TABLE … USING INDEX`` comes back as an
opaque ``Command``. None of these clauses is part of a logical model, so they
are removed; each removal is a named rule, applied in order, and reported with
how many times it fired.

Rules match only outside string literals and quoted identifiers: both are
masked before any rule runs and restored after, so a CHECK constraint's
``'CANCELLED'`` or a column called ``"TABLESPACE"`` can never be touched.

Partitioning is the exception. A ``PARTITION BY`` clause carries
design intent, so it is removed from the statement but **returned** as the
table's partitioning metadata, never discarded.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

_QUOTED = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"")
_MASK = "\x00{}\x00"
_MASKED = re.compile(r"\x00(\d+)\x00")


def _mask(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def keep(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return _MASK.format(len(saved) - 1)

    return _QUOTED.sub(keep, text), saved


def _unmask(text: str, saved: list[str]) -> str:
    return _MASKED.sub(lambda m: saved[int(m.group(1))], text)


def _balanced_end(text: str, open_index: int) -> int:
    """Index just past the parenthesis matching the one at ``open_index``."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _remove_keyword_with_parens(text: str, keyword: str) -> tuple[str, int]:
    """Remove every ``KEYWORD ( … )`` with balanced parentheses."""
    pattern = re.compile(rf"\b{keyword}\s*\(", re.IGNORECASE)
    count = 0
    while (match := pattern.search(text)) is not None:
        end = _balanced_end(text, match.end() - 1)
        text = text[: match.start()] + " " + text[end:]
        count += 1
    return text, count


_LOB = re.compile(
    r"\bLOB\s*\([^()]*\)\s*STORE\s+AS\s+(?:(?:SECUREFILE|BASICFILE)\s+)?(?:\x00\d+\x00\s*)?",
    re.IGNORECASE,
)


def _remove_lob_storage(text: str) -> tuple[str, int]:
    """Remove ``LOB (cols) STORE AS [SECUREFILE|BASICFILE] [segment] ( … )``."""
    count = 0
    while (match := _LOB.search(text)) is not None:
        end = match.end()
        if end < len(text) and text[end] == "(":
            end = _balanced_end(text, end)
        text = text[: match.start()] + " " + text[end:]
        count += 1
    return text, count


def _sub(pattern: str) -> Callable[[str], tuple[str, int]]:
    compiled = re.compile(pattern, re.IGNORECASE)

    def rule(text: str) -> tuple[str, int]:
        return compiled.subn(" ", text)

    return rule


@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    apply: Callable[[str], tuple[str, int]]


# Order matters only where one clause contains another: a LOB storage clause
# (which holds its own STORAGE and TABLESPACE) goes first, STORAGE(...) before
# the segment attributes that can sit inside it, and USING INDEX last, once the
# attributes that can follow it are gone.
RULES: tuple[Rule, ...] = (
    Rule("lob_storage", "LOB ( … ) STORE AS [SECUREFILE|BASICFILE] ( … ), a LOB column's storage",
         _remove_lob_storage),
    Rule("storage", "STORAGE ( … ) clauses",
         lambda t: _remove_keyword_with_parens(t, "STORAGE")),
    Rule("tablespace", "TABLESPACE <name>",
         _sub(r"\bTABLESPACE\s+(?:\x00\d+\x00|\w+)")),
    Rule("segment_attributes",
         "SEGMENT CREATION, PCTFREE, PCTUSED, INITRANS, MAXTRANS, PCTTHRESHOLD",
         _sub(r"\bSEGMENT\s+CREATION\s+(?:IMMEDIATE|DEFERRED)\b"
              r"|\b(?:PCTFREE|PCTUSED|INITRANS|MAXTRANS|PCTTHRESHOLD)\s+\d+")),
    Rule("logging_compression", "LOGGING, NOLOGGING, COMPRESS and NOCOMPRESS",
         _sub(r"\b(?:NO)?LOGGING\b|\bNOCOMPRESS\b"
              r"|\b(?:ROW\s+STORE\s+|COLUMN\s+STORE\s+)?COMPRESS(?:\s+(?:BASIC|ADVANCED|FOR\s+\w+(?:\s+\w+)?))?\b")),
    Rule("organization_index", "ORGANIZATION INDEX (an index-organized table)",
         _sub(r"\bORGANIZATION\s+INDEX\b")),
    Rule("identity_options",
         "sequence options after AS IDENTITY (MINVALUE … NOSCALE)",
         _sub(r"(?<=\bIDENTITY)(?:\s+(?:MINVALUE\s+-?\d+|MAXVALUE\s+-?\d+|INCREMENT\s+BY\s+-?\d+"
              r"|START\s+WITH\s+-?\d+|CACHE\s+\d+|NOCACHE|NOORDER|ORDER|NOCYCLE|CYCLE"
              r"|NOKEEP|KEEP|NOSCALE|SCALE(?:\s+(?:NO)?EXTEND)?))+")),
    Rule("constraint_state", "ENABLE, DISABLE, VALIDATE, NOVALIDATE, RELY, NORELY",
         _sub(r"\b(?:ENABLE|DISABLE|NOVALIDATE|VALIDATE|NORELY|RELY)\b")),
    # A key declared inside CREATE TABLE writes its index's build options
    # after USING INDEX (found by the drifted HR fixture, Sprint 8 Step 5:
    # a primary key added by ALTER TABLE is exported inline).
    Rule("index_statistics", "COMPUTE STATISTICS, an index build option after USING INDEX",
         _sub(r"\bCOMPUTE\s+STATISTICS\b")),
    Rule("using_index", "USING INDEX, with the index's name if one is given",
         _sub(r"\bUSING\s+INDEX(?:\s+\x00\d+\x00(?:\.\x00\d+\x00)?)?")),
)

_PARTITION_BY = re.compile(r"\bPARTITION\s+BY\s+(RANGE|LIST|HASH|REFERENCE)\s*\(", re.IGNORECASE)


@dataclass
class Normalized:
    text: str
    applied: dict[str, int] = field(default_factory=dict)
    partitioning: str | None = None


def _take_partitioning(masked: str, saved: list[str]) -> tuple[str, str | None]:
    """Remove a table's PARTITION BY clause to the end, returning it as metadata."""
    match = _PARTITION_BY.search(masked)
    if match is None:
        return masked, None
    clause = masked[match.start():].rstrip().rstrip(";").strip()
    return masked[: match.start()], " ".join(_unmask(clause, saved).split())


def normalize(statement: str, disabled: frozenset[str] = frozenset()) -> Normalized:
    """Apply every rule not in ``disabled`` to one Oracle statement.

    ``disabled`` exists for the negative controls: each rule's test turns it
    off and shows the statement then fails to import.
    """
    masked, saved = _mask(statement)
    result = Normalized(text=statement)
    if "partition_by" not in disabled:
        masked, result.partitioning = _take_partitioning(masked, saved)
        if result.partitioning:
            result.applied["partition_by"] = 1
    for rule in RULES:
        if rule.name in disabled:
            continue
        masked, count = rule.apply(masked)
        if count:
            result.applied[rule.name] = count
    # Removing clauses leaves runs of spaces, and commas left dangling before a
    # closing parenthesis are not an issue sqlglot has; the text is kept as is.
    result.text = re.sub(r"[ \t]+", " ", _unmask(masked, saved))
    return result


RULE_NAMES: tuple[str, ...] = ("partition_by", *(rule.name for rule in RULES))
