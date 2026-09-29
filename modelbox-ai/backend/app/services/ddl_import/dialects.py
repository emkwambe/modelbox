"""The dialects a DDL file can be imported from, and the evidence behind each.

One list, served to the UI by the API, so no surface can offer a dialect or
describe its evidence differently. ``evidence`` says what the import has been
tested against: ``genuine export`` means fixtures written by the database's own
export tool (``tests/fixtures/ddl/``); ``documentation-derived`` means a
fixture hand-written from the vendor's documentation, which has never met real
tool output. SQL Server joins in Sprint 8 Step 2b.
"""

from __future__ import annotations

IMPORT_DIALECTS: dict[str, dict[str, str]] = {
    "oracle": {
        "label": "Oracle",
        "evidence": "genuine export",
        "tool": "DBMS_METADATA.GET_DDL, or any export with SQL*Plus terminators",
    },
    "postgres": {
        "label": "PostgreSQL",
        "evidence": "genuine export",
        "tool": "pg_dump --schema-only",
    },
    "snowflake": {
        "label": "Snowflake",
        "evidence": "documentation-derived",
        "tool": "GET_DDL, as Snowflake's documentation shows its output",
    },
}
