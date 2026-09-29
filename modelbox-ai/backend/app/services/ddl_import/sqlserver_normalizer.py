"""Strip the physical clauses of SQL Server export DDL before it is parsed.

SSMS and SMO write clauses sqlglot cannot parse (research R1): ``ROWGUIDCOL``
fails a CREATE TABLE outright, and ``ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]``
turns it into an opaque ``Command``. None is part of a logical model, so each
is removed by a named rule, and the report counts how often each fired.

R1's prototype stripped ``WITH ( … )`` greedily and lost a primary key with
it. Here the index-option rule removes only a balanced ``WITH ( … )`` whose
contents are option assignments (``PAD_INDEX = OFF, …``), so the constraint it
follows is left intact; a named regression test holds that.

Rules match only outside string literals and quoted or bracketed identifiers,
which are masked first and restored after: a column called ``[ON]`` or a
default of ``N'TEXTIMAGE_ON'`` is never touched. A partition scheme
(``ON [scheme] ( column )``) is kept as the table's partitioning metadata.

``WITH CHECK`` / ``WITH NOCHECK`` before ``ADD`` says whether existing rows are
validated; the constraint is the same either way. sqlglot returns an opaque
``Command`` for the NOCHECK form, so both are removed and NOCHECK is recorded.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

_QUOTED = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|\[[^\]]*\]")
_MASK = "\x00{}\x00"
_MASKED = re.compile(r"\x00(\d+)\x00")
_M = r"\x00\d+\x00"


def _mask(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def keep(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return _MASK.format(len(saved) - 1)

    return _QUOTED.sub(keep, text), saved


def _unmask(text: str, saved: list[str]) -> str:
    return _MASKED.sub(lambda m: saved[int(m.group(1))], text)


def _balanced_end(text: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


_OPTION_LIST = re.compile(rf"^\(\s*(?:{_M}|\w+)\s*=", re.IGNORECASE)


def _remove_index_options(text: str) -> tuple[str, int]:
    """Remove ``WITH ( NAME = value, … )``, and only that form of WITH."""
    count, start = 0, 0
    pattern = re.compile(r"\bWITH\s*(?=\()", re.IGNORECASE)
    while (match := pattern.search(text, start)) is not None:
        open_at = match.end()
        end = _balanced_end(text, open_at)
        if _OPTION_LIST.match(text[open_at:end]):
            text = text[: match.start()] + " " + text[end:]
            count += 1
            start = match.start()
        else:
            start = end
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


RULES: tuple[Rule, ...] = (
    Rule("rowguidcol", "ROWGUIDCOL", _sub(r"\bROWGUIDCOL\b")),
    Rule("not_for_replication", "NOT FOR REPLICATION", _sub(r"\bNOT\s+FOR\s+REPLICATION\b")),
    Rule("index_options", "WITH ( PAD_INDEX = OFF, … ): an index's options", _remove_index_options),
    Rule("textimage_on", "TEXTIMAGE_ON [filegroup] and FILESTREAM_ON [filegroup]",
         _sub(rf"\b(?:TEXTIMAGE_ON|FILESTREAM_ON)\s+{_M}")),
    Rule("filegroup", "ON [filegroup], where a table or index is stored",
         _sub(rf"\bON\s+{_M}(?!\s*[.(])")),
    Rule("clustering", "CLUSTERED and NONCLUSTERED on a key", _sub(r"\b(?:NON)?CLUSTERED\b")),
    # The sort order of a key's index. The parser takes it inside PRIMARY KEY
    # but not inside UNIQUE, and it is not part of the logical key.
    Rule("key_order", "ASC and DESC in a key's column list", _sub(r"\b(?:ASC|DESC)\b")),
    # Typed XML: the column's source_data_type keeps the declaration verbatim,
    # so dropping the collection from the text to parse loses nothing.
    Rule("xml_schema_collection", "xml ( CONTENT | DOCUMENT [schema].[collection] )",
         lambda t: re.subn(rf"({_M})\s*\(\s*(?:CONTENT|DOCUMENT)\s+{_M}(?:\s*\.\s*{_M})?\s*\)",
                           r"\1", t, flags=re.IGNORECASE)),
)

_PARTITION_SCHEME = re.compile(rf"\bON\s+({_M})\s*\(\s*({_M}|\w+)\s*\)", re.IGNORECASE)
_CHECK_MODE = re.compile(r"\bWITH\s+(NO)?CHECK\s+(?=ADD\b)", re.IGNORECASE)


@dataclass
class Normalized:
    text: str
    applied: dict[str, int] = field(default_factory=dict)
    partitioning: str | None = None
    nocheck: bool = False  # ALTER TABLE … WITH NOCHECK ADD: not validated against existing rows


def normalize(statement: str, disabled: frozenset[str] = frozenset()) -> Normalized:
    """Apply every rule not in ``disabled`` to one T-SQL batch."""
    masked, saved = _mask(statement)
    result = Normalized(text=statement)
    if "partition_scheme" not in disabled and (match := _PARTITION_SCHEME.search(masked)):
        result.partitioning = " ".join(_unmask(match.group(0), saved).split())
        masked = masked[: match.start()] + " " + masked[match.end():]
        result.applied["partition_scheme"] = 1
    if "check_mode" not in disabled and (match := _CHECK_MODE.search(masked)):
        # WITH CHECK / WITH NOCHECK before ADD: whether existing rows are
        # validated. The constraint is the same either way; NOCHECK is recorded.
        result.nocheck = bool(match.group(1))
        masked = masked[: match.start()] + masked[match.end():]
        result.applied["check_mode"] = 1
    for rule in RULES:
        if rule.name in disabled:
            continue
        masked, count = rule.apply(masked)
        if count:
            result.applied[rule.name] = count
    result.text = re.sub(r"[ \t]+", " ", _unmask(masked, saved))
    return result


RULE_NAMES: tuple[str, ...] = ("partition_scheme", "check_mode", *(rule.name for rule in RULES))
