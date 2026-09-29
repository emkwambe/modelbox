#!/usr/bin/env python3
"""Export Oracle sample schemas with DBMS_METADATA, and count them from the catalog.

Runs in CI (``.github/workflows/ddl-fixtures.yml``) against an Oracle Database
Free container into which the HR and CO sample schemas were installed. For each
schema it writes two files:

* ``<schema>.sql``: every table as ``DBMS_METADATA.GET_DDL('TABLE', …)``
  returns it, with the default transform parameters (storage, segment
  attributes, tablespace and constraints all included), followed by the
  table's comments from ``GET_DEPENDENT_DDL('COMMENT', …)``. The one parameter
  changed is ``SQLTERMINATOR``, so the file can be split into statements, as it
  is in any export saved to a file;
* ``<schema>.manifest.json``: the counts an import must reconcile against,
  **read from the catalog views**, never from a parser.

Usage::

    python oracle_export.py --dsn 127.0.0.1:1521/FREEPDB1 --schema HR --out DIR \\
        --image IMAGE@DIGEST --source "oracle-samples/db-sample-schemas@SHA human_resources/hr_create.sql" \\
        --run RUN_URL

The password for SYSTEM comes from ``ORACLE_PASSWORD``; it is never printed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import oracledb

HEADER_END = "-- end of provenance"

# Constraint and comment counts, per table, from the catalog. NOT NULL is
# stored as a CHECK constraint in Oracle; it is counted apart from real CHECKs
# (SEARCH_CONDITION_VC is the VARCHAR2 form of the condition).
PER_TABLE = """
SELECT t.table_name,
       (SELECT COUNT(*) FROM all_tab_columns c
         WHERE c.owner = t.owner AND c.table_name = t.table_name) AS columns,
       (SELECT COUNT(*) FROM all_constraints k
         WHERE k.owner = t.owner AND k.table_name = t.table_name
           AND k.constraint_type = 'P') AS primary_keys,
       (SELECT COUNT(*) FROM all_constraints k
         WHERE k.owner = t.owner AND k.table_name = t.table_name
           AND k.constraint_type = 'R') AS foreign_keys,
       (SELECT COUNT(*) FROM all_constraints k
         WHERE k.owner = t.owner AND k.table_name = t.table_name
           AND k.constraint_type = 'U') AS unique_constraints,
       (SELECT COUNT(*) FROM all_constraints k
         WHERE k.owner = t.owner AND k.table_name = t.table_name
           AND k.constraint_type = 'C'
           AND NOT REGEXP_LIKE(k.search_condition_vc, '^"[^"]+" IS NOT NULL$')) AS check_constraints,
       (SELECT COUNT(*) FROM all_constraints k
         WHERE k.owner = t.owner AND k.table_name = t.table_name
           AND k.constraint_type = 'C'
           AND REGEXP_LIKE(k.search_condition_vc, '^"[^"]+" IS NOT NULL$')) AS not_null_constraints,
       (SELECT COUNT(*) FROM all_tab_comments m
         WHERE m.owner = t.owner AND m.table_name = t.table_name
           AND m.comments IS NOT NULL) AS table_descriptions,
       (SELECT COUNT(*) FROM all_col_comments m
         WHERE m.owner = t.owner AND m.table_name = t.table_name
           AND m.comments IS NOT NULL) AS column_descriptions
  FROM all_tables t
 WHERE t.owner = :owner AND t.nested = 'NO' AND t.secondary = 'N'
   AND (t.iot_type IS NULL OR t.iot_type = 'IOT') AND t.dropped = 'NO'
 ORDER BY t.table_name
"""

COUNT_KEYS = (
    "columns", "primary_keys", "foreign_keys", "unique_constraints",
    "check_constraints", "not_null_constraints", "table_descriptions",
    "column_descriptions",
)


def _set_transforms(cursor: oracledb.Cursor) -> None:
    cursor.execute(
        "BEGIN DBMS_METADATA.SET_TRANSFORM_PARAM("
        "DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE); END;"
    )


def _comments(cursor: oracledb.Cursor, table: str, owner: str) -> str | None:
    try:
        cursor.execute(
            "SELECT DBMS_METADATA.GET_DEPENDENT_DDL('COMMENT', :t, :o) FROM dual",
            t=table, o=owner,
        )
    except oracledb.DatabaseError as exc:
        (error,) = exc.args
        if error.code == 31608:  # "specified object … not found": the table has no comments
            return None
        raise
    return cursor.fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    owner = args.schema.upper()

    oracledb.defaults.fetch_lobs = False
    connection = oracledb.connect(
        user="system", password=os.environ["ORACLE_PASSWORD"], dsn=args.dsn
    )
    cursor = connection.cursor()
    cursor.execute("SELECT banner_full FROM v$version")
    version = " ".join(cursor.fetchone()[0].split())

    cursor.execute(PER_TABLE, owner=owner)
    names = [d[0].lower() for d in cursor.description]
    tables = [dict(zip(names, row)) for row in cursor.fetchall()]
    if not tables:
        print(f"::error::no tables found for {owner}; the sample schema did not install")
        return 1

    _set_transforms(cursor)
    body: list[str] = []
    for table in tables:
        cursor.execute(
            "SELECT DBMS_METADATA.GET_DDL('TABLE', :t, :o) FROM dual",
            t=table["table_name"], o=owner,
        )
        body.append(cursor.fetchone()[0])
        comments = _comments(cursor, table["table_name"], owner)
        if comments:
            body.append(comments)

    today = datetime.date.today().isoformat()
    header = [
        "-- ModelBox DDL fixture: genuine tool output. Do not edit; regenerate it.",
        f"-- source: {args.source} (MIT; see ../README.md)",
        f"-- tool: DBMS_METADATA.GET_DDL('TABLE') and GET_DEPENDENT_DDL('COMMENT'), {version}",
        "-- transform parameters: defaults, except SQLTERMINATOR = TRUE",
        f"-- client: python-oracledb {oracledb.__version__} (thin mode)",
        f"-- image: {args.image}",
        f"-- generated: {today} by {args.run}",
        HEADER_END,
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    stem = owner.lower()
    (args.out / f"{stem}.sql").write_text(
        "\n".join(header) + "\n" + "\n".join(body).rstrip() + "\n", encoding="utf-8"
    )

    totals = {key: sum(int(t[key]) for t in tables) for key in COUNT_KEYS}
    manifest = {
        "fixture": f"{stem}.sql",
        "dialect": "oracle",
        "schema": owner,
        "counts_from": "catalog views (ALL_TABLES, ALL_TAB_COLUMNS, ALL_CONSTRAINTS, ALL_TAB_COMMENTS, ALL_COL_COMMENTS)",
        "counts": {"tables": len(tables), **totals},
        "tables": [
            {"name": t["table_name"], **{key: int(t[key]) for key in COUNT_KEYS}} for t in tables
        ],
        "catalog_query": " ".join(PER_TABLE.split()),
        "generated": today,
        "run": args.run,
    }
    (args.out / f"{stem}.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{owner}: {len(tables)} tables, counts {manifest['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
