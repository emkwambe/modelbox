"""Seed / export / inspect helper for the migration verification (Task 5).

Run as a subprocess inside a *specific checkout* of the backend, so the
pre-migration side is produced by v1.6.0's code and the post-migration side by
the current tree. It therefore uses only APIs present in both versions.

Emits ``@@RESULT@@`` followed by JSON on stdout.

    python _migration_helper.py {seed-and-export|export-only|inspect-backfill} <gold_dir>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.metadata_store import DataModel, Workspace
from app.schemas.data_model import SynthesizedModel
from app.services.exporter_service import ExporterService
from app.services.graph_repository import GraphRepository
from app.services.synthesis_engine import SynthesisEngine

DIALECTS = ("postgres", "snowflake", "databricks", "bigquery", "duckdb",
            "redshift", "clickhouse")


def load_gold(gold_dir: Path) -> list[tuple[str, SynthesizedModel]]:
    out = []
    for path in sorted(gold_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        out.append((
            raw["id"],
            SynthesizedModel.model_validate({
                "paradigm": raw["paradigm"],
                "entities": raw["entities"],
                "relationships": raw["relationships"],
            }),
        ))
    return out


def export_all(model: SynthesizedModel, dataset: str) -> dict[str, str]:
    """Every artifact the product can emit, keyed by a stable path."""
    svc = ExporterService()
    files: dict[str, str] = {}
    for dialect in DIALECTS:
        files[f"ddl/{dialect}.sql"] = svc.generate_ddl(model, dialect)
    for path, content in svc.generate_dbt_project(model).items():
        files[f"dbt/{path}"] = content
    for path, content in svc.generate_cube_schema(model).items():
        files[f"cube/{path}"] = content
    for engine in ("lookml", "metricflow"):
        for path, content in svc.export_semantic_layer(model, engine).items():
            files[f"semantic/{engine}/{path}"] = content
    for fmt in ("odcs", "avro", "protobuf"):
        for path, content in svc.export_data_contract(model, fmt, dataset).items():
            files[f"contract/{fmt}/{path}"] = content
    for fmt in ("markdown", "html", "json"):
        for path, content in svc.export_data_dictionary(model, fmt, dataset).items():
            files[f"dict/{fmt}/{path}"] = content
    for fmt in ("sql_insert", "csv"):
        seed = svc.generate_synthetic_seed(model, 10, fmt, "postgres")
        for path, content in seed.files.items():
            files[f"seed/{fmt}/{path}"] = content
    return files


async def seed(session: AsyncSession, gold: list) -> None:
    workspace = Workspace(name="migration-verification")
    session.add(workspace)
    await session.flush()
    for title, model in gold:
        row = DataModel(
            workspace_id=workspace.workspace_id,
            title=title,
            current_paradigm=str(model.paradigm),
            target_dialect="postgres",
        )
        session.add(row)
        await session.flush()
        await GraphRepository(session).replace_graph(
            row.model_id, model.entities, model.relationships
        )
    await session.commit()


async def export_persisted(session: AsyncSession) -> dict[str, dict[str, str]]:
    """Read every seeded model back out of the database and export it."""
    engine = SynthesisEngine(session, None)  # get_model needs no gateway
    out: dict[str, dict[str, str]] = {}
    rows = (await session.execute(select(DataModel).order_by(DataModel.title))).scalars().all()
    for row in rows:
        response = await engine.get_model(row.model_id)
        model = SynthesizedModel(
            paradigm=response.paradigm,
            entities=response.entities,
            relationships=response.relationships,
            suggested_metrics=response.suggested_metrics,
        )
        out[row.title] = export_all(model, row.title)
    return out


async def inspect_backfill(session: AsyncSession) -> dict:
    """Dump stable_id state straight from SQL, independent of the ORM."""
    rows = (await session.execute(text(
        """
        SELECT m.title, e.entity_id, e.entity_name, e.next_stable_id,
               c.column_name, c.stable_id, c.is_primary_key, c.is_nullable,
               c.ordinal_position
        FROM model_entities e
        JOIN data_models m ON m.model_id = e.model_id
        JOIN entity_columns c ON c.entity_id = e.entity_id
        ORDER BY m.title, e.entity_name, c.ordinal_position, c.column_id
        """
    ))).mappings().all()
    entities: dict[str, dict] = {}
    for r in rows:
        # Keyed by entity_id, not entity_name: the same name legitimately
        # occurs in several models (dim_customer is in two gold graphs), and
        # grouping by name merges them into one nonsensical id sequence.
        entity = entities.setdefault(
            str(r["entity_id"]),
            {"entity_name": f"{r['title']}.{r['entity_name']}",
             "next_stable_id": r["next_stable_id"], "columns": []},
        )
        entity["columns"].append({
            "column_name": r["column_name"],
            "stable_id": r["stable_id"],
            "is_primary_key": bool(r["is_primary_key"]),
            "is_nullable": bool(r["is_nullable"]),
        })
    return {"entities": list(entities.values())}


async def main() -> None:
    mode, gold_dir = sys.argv[1], Path(sys.argv[2])
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            if mode == "seed-and-export":
                await seed(session, load_gold(gold_dir))
                result = {"models": await export_persisted(session)}
            elif mode == "export-only":
                result = {"models": await export_persisted(session)}
            elif mode == "inspect-backfill":
                result = await inspect_backfill(session)
            else:
                raise SystemExit(f"unknown mode: {mode}")
    finally:
        await engine.dispose()
    sys.stdout.write("@@RESULT@@" + json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
