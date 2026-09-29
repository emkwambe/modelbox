"""Split an exported DDL file into statements, per dialect.

A lexer, not a line-based guess: it knows single-quoted strings (with ``''``),
double-quoted identifiers, ``--`` and ``/* */`` comments, and PostgreSQL's
``$tag$ … $tag$`` bodies, so a ``;`` inside any of them never ends a statement.

Every statement is kept and classified, never dropped:

* ``client``: a line for the client, not the database (SQL*Plus's ``SET``,
  ``PROMPT``, ``@script``, ``WHENEVER …``; psql's ``\\restrict``, ``\\connect``);
* ``procedural``: a procedure, function, package, trigger or anonymous block.
  Oracle's end at a line holding only ``/``, PostgreSQL's and Snowflake's at
  the ``;`` after their ``$$`` body. They are not imported, and the report
  lists them;

T-SQL is split into batches at ``GO`` lines instead: each batch is one
statement, which is how SSMS and SMO write them and how SQL Server runs them.
* ``sql``: everything else, for the importer to classify and parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SQLPLUS_COMMANDS = re.compile(
    r"^(?:REM(?:ARK)?|PRO(?:MPT)?|SET|SPO(?:OL)?|WHENEVER|DEF(?:INE)?|UNDEF(?:INE)?"
    r"|CONN(?:ECT)?|EXIT|QUIT|COL(?:UMN)?|SHOW|TTITLE|BTITLE|BREAK|COMPUTE|CLEAR"
    r"|PAUSE|ACCEPT|VAR(?:IABLE)?|EXEC(?:UTE)?|DESC(?:RIBE)?)\b|^@",
    re.IGNORECASE,
)
ORACLE_PROCEDURAL = re.compile(
    r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?"
    r"(?:PROCEDURE|FUNCTION|PACKAGE(?:\s+BODY)?|TRIGGER|TYPE\s+BODY|LIBRARY|JAVA)\b"
    r"|DECLARE\b|BEGIN\b)",
    re.IGNORECASE,
)
POSTGRES_PROCEDURAL = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?"
    r"(?:FUNCTION|PROCEDURE|TRIGGER|AGGREGATE|RULE|EVENT\s+TRIGGER)\b",
    re.IGNORECASE,
)
SNOWFLAKE_PROCEDURAL = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?(?:PROCEDURE|FUNCTION|TASK)\b",
    re.IGNORECASE,
)
TSQL_PROCEDURAL = re.compile(
    r"^CREATE\s+(?:OR\s+ALTER\s+)?(?:PROC(?:EDURE)?|FUNCTION|TRIGGER)\b",
    re.IGNORECASE,
)
# SSMS and SMO end each batch with a line holding only GO (optionally a count).
_GO = re.compile(r"^[ \t]*GO(?:[ \t]+\d+)?[ \t]*$", re.IGNORECASE | re.MULTILINE)
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$")

DIALECTS = ("oracle", "postgres", "snowflake", "tsql")
_PROCEDURAL = {"postgres": POSTGRES_PROCEDURAL, "snowflake": SNOWFLAKE_PROCEDURAL}


@dataclass(frozen=True)
class Statement:
    index: int  # 1-based position among the file's statements
    line: int  # line on which the statement starts
    text: str
    kind: str  # "sql", "client" or "procedural"

    @property
    def head(self) -> str:
        """The statement's first words, for naming it in a report."""
        return " ".join(self.text.split()[:6])[:120]


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end == -1 else end + 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            break
    return i


def _line_end(text: str, i: int) -> int:
    end = text.find("\n", i)
    return len(text) if end == -1 else end


def _scan_to_semicolon(text: str, i: int, dollar_quotes: bool) -> int:
    """Index just past the ``;`` ending the statement at ``i``, or the end."""
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif ch == '"':
            end = text.find('"', i + 1)
            i = n if end == -1 else end + 1
        elif text.startswith("--", i):
            i = _line_end(text, i)
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif dollar_quotes and ch == "$" and (match := _DOLLAR_TAG.match(text, i)):
            end = text.find(match.group(0), match.end())
            i = n if end == -1 else end + len(match.group(0))
        elif ch == ";":
            return i + 1
        else:
            i += 1
    return n


def _scan_to_slash_line(text: str, i: int) -> tuple[int, int]:
    """Oracle PL/SQL: (end of the block's text, index past its ``/`` line)."""
    for match in re.finditer(r"^[ \t]*/[ \t]*$", text[i:], re.MULTILINE):
        start = i + match.start()
        return start, i + match.end()
    return len(text), len(text)


def _split_batches(text: str) -> list[Statement]:
    """T-SQL: each batch between GO lines is one statement, as SQL Server runs it."""
    statements: list[Statement] = []
    start = 0
    for boundary in [*_GO.finditer(text), None]:
        end = boundary.start() if boundary is not None else len(text)
        chunk = text[start:end]
        offset = _skip_ws_and_comments(chunk, 0)
        body = chunk[offset:].strip()
        if body:
            line = text.count("\n", 0, start + offset) + 1
            kind = "procedural" if TSQL_PROCEDURAL.match(body) else "sql"
            statements.append(Statement(len(statements) + 1, line, body, kind))
        start = boundary.end() if boundary is not None else len(text)
    return statements


def split(text: str, dialect: str) -> list[Statement]:
    if dialect not in DIALECTS:
        raise ValueError(f"no statement splitter for dialect {dialect!r}")
    if dialect == "tsql":
        return _split_batches(text)
    statements: list[Statement] = []
    i, n = 0, len(text)
    while True:
        i = _skip_ws_and_comments(text, i)
        if i >= n:
            break
        line = text.count("\n", 0, i) + 1
        rest = text[i: _line_end(text, i)]
        if dialect == "oracle" and rest.strip() == "/":
            i = _line_end(text, i)  # a stray terminator after a ';'
            continue
        if (dialect == "oracle" and SQLPLUS_COMMANDS.match(rest)) or (
            dialect == "postgres" and rest.startswith("\\")
        ):
            end = _line_end(text, i)
            kind, body = "client", text[i:end]
        elif dialect == "oracle" and ORACLE_PROCEDURAL.match(rest):
            body_end, end = _scan_to_slash_line(text, i)
            kind, body = "procedural", text[i:body_end]
        else:
            # Snowflake also delimits procedure bodies with $$.
            end = _scan_to_semicolon(text, i, dollar_quotes=dialect != "oracle")
            body = text[i:end]
            procedural = _PROCEDURAL.get(dialect)
            kind = "procedural" if procedural is not None and procedural.match(rest) else "sql"
        statements.append(Statement(len(statements) + 1, line, body.strip(), kind))
        i = end
    return statements
