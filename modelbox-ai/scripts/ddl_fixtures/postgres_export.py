#!/usr/bin/env python3
"""Export a PostgreSQL sample schema with pg_dump, and count it from the catalog.

Runs in CI (``.github/workflows/ddl-fixtures.yml``) against the appliance's own
pinned PostgreSQL image, into which the Pagila sample schema was loaded. It
writes two files:

* ``<name>.sql``: ``pg_dump --schema-only`` exactly as the server's own pg_dump
  prints it, run inside the container. The one option added is a fixed
  ``--restrict-key``: pg_dump otherwise writes a random key into its
  ``\\restrict`` line on every run, and a fixture must be reproducible;
* ``<name>.manifest.json``: the counts an import must reconcile against, **read
  from the pg_catalog views**, never from a parser. Every constraint the catalog
  holds on a table is counted, and those a partition inherits from its parent
  (``conparentid <> 0``) are also counted apart: pg_dump writes each
  partition's inherited primary key as its own ``ADD CONSTRAINT``, so an
  importer meets them in the text, and a reconciliation must know which they are.

Usage::

    python postgres_export.py --container NAME --user postgres --database pagila \\
        --dsn-port PORT --out DIR --image IMAGE@DIGEST --source SOURCE --run RUN_URL

The password comes from ``PGPASSWORD``; it is never printed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

HEADER_END = "-- end of provenance"
RESTRICT_KEY = "modelboxfixture"

PER_TABLE = """
SELECT c.relname AS name,
       CASE c.relkind WHEN 'p' THEN 'partitioned' ELSE 'table' END AS kind,
       (SELECT p.relname FROM pg_inherits i JOIN pg_class p ON p.oid = i.inhparent
         WHERE i.inhrelid = c.oid) AS partition_of,
       (SELECT count(*) FROM pg_attribute a
         WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS columns,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'p') AS primary_keys,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'p' AND k.conparentid <> 0) AS primary_keys_inherited,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'f') AS foreign_keys,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'f' AND k.conparentid <> 0) AS foreign_keys_inherited,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'u') AS unique_constraints,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'u' AND k.conparentid <> 0) AS unique_constraints_inherited,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'c') AS check_constraints,
       (SELECT count(*) FROM pg_constraint k
         WHERE k.conrelid = c.oid AND k.contype = 'c' AND k.conparentid <> 0) AS check_constraints_inherited,
       (SELECT count(*) FROM pg_attribute a
         WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped AND a.attnotnull) AS not_null_columns,
       (SELECT count(*) FROM pg_description d
         WHERE d.classoid = 'pg_class'::regclass AND d.objoid = c.oid AND d.objsubid = 0) AS table_descriptions,
       (SELECT count(*) FROM pg_description d
         WHERE d.classoid = 'pg_class'::regclass AND d.objoid = c.oid AND d.objsubid > 0) AS column_descriptions
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
 ORDER BY c.relname
"""

COUNT_KEYS = (
    "columns", "primary_keys", "primary_keys_inherited", "foreign_keys",
    "foreign_keys_inherited", "unique_constraints", "unique_constraints_inherited",
    "check_constraints", "check_constraints_inherited", "not_null_columns",
    "table_descriptions", "column_descriptions",
)
NOTE = (
    "Constraint counts are every constraint the catalog holds on the table; the "
    "*_inherited counts are those a partition inherits from its parent. pg_dump "
    "writes each partition's inherited primary key as its own ADD CONSTRAINT. "
    "CHECK constraints on domains are not table constraints and are not counted."
)


def _in_container(container: str, *argv: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD", container, *argv],
        capture_output=True, text=True, check=True,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--container", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--dsn-port", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()

    dump = _in_container(
        args.container, "pg_dump", "--schema-only", f"--restrict-key={RESTRICT_KEY}",
        "-U", args.user, "-d", args.database,
    )
    tool_version = _in_container(args.container, "pg_dump", "--version").strip()

    connection = psycopg2.connect(
        host="127.0.0.1", port=args.dsn_port, user=args.user,
        password=os.environ["PGPASSWORD"], dbname=args.database,
    )
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version")
        server_version = cursor.fetchone()[0]
        cursor.execute(PER_TABLE)
        names = [d[0] for d in cursor.description]
        tables = [dict(zip(names, row)) for row in cursor.fetchall()]
    connection.close()
    if not tables:
        print("::error::no tables found in public; the sample schema did not load")
        return 1

    today = datetime.date.today().isoformat()
    header = [
        "-- ModelBox DDL fixture: genuine tool output. Do not edit; regenerate it.",
        f"-- source: {args.source} (MIT; see ../README.md)",
        f"-- tool: {tool_version}, server PostgreSQL {server_version}",
        f"-- options: --schema-only --restrict-key={RESTRICT_KEY} (the key is otherwise random per run)",
        f"-- image: {args.image}",
        f"-- generated: {today} by {args.run}",
        HEADER_END,
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.database
    (args.out / f"{stem}.sql").write_text("\n".join(header) + "\n" + dump, encoding="utf-8")

    totals = {key: sum(int(t[key]) for t in tables) for key in COUNT_KEYS}
    manifest = {
        "fixture": f"{stem}.sql",
        "dialect": "postgres",
        "schema": "public",
        "counts_from": "catalog views (pg_class, pg_attribute, pg_constraint, pg_inherits, pg_description)",
        "note": NOTE,
        "counts": {
            "tables": len(tables),
            "partitions": sum(1 for t in tables if t["partition_of"]),
            **totals,
        },
        "tables": [
            {"name": t["name"], "kind": t["kind"], "partition_of": t["partition_of"],
             **{key: int(t[key]) for key in COUNT_KEYS}}
            for t in tables
        ],
        "catalog_query": " ".join(PER_TABLE.split()),
        "generated": today,
        "run": args.run,
    }
    (args.out / f"{stem}.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{stem}: {len(tables)} tables, counts {manifest['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
