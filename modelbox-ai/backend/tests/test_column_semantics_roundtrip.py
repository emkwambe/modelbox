"""Declared column semantics (is_metric/aggregation) survive persist -> reload."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models.metadata_store import Base, User, Workspace, WorkspaceMember
from app.schemas.data_model import (
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
    SynthesizeRequest,
)
from app.services.synthesis_engine import SynthesisEngine


class _StubGateway:
    def __init__(self, model: SynthesizedModel) -> None:
        self._model = model

    async def structured_completion(
        self, task: str, prompt: str, response_model: type[Any], **_: Any
    ) -> SynthesizedModel:
        return self._model


def _model() -> SynthesizedModel:
    return SynthesizedModel(
        paradigm="KIMBALL",  # type: ignore[arg-type]
        entities=[
            EntitySchema(
                entity_name="fact_reviews",
                entity_type="FACT",  # type: ignore[arg-type]
                grain="per review",
                tier="TIER_1_CRITICAL",  # type: ignore[arg-type]
                freshness_sla="< 4h",
                columns=[
                    ColumnSchema(name="review_id", data_type="INT", is_primary_key=True),
                    # a declared measure on a non-numeric column
                    ColumnSchema(
                        name="rating",
                        data_type="VARCHAR(8)",
                        is_metric=True,
                        aggregation="AVG",
                    ),
                    # declared quality rules (Sprint U3)
                    ColumnSchema(
                        name="stars",
                        data_type="INT",
                        min_value=1,
                        max_value=5,
                    ),
                    ColumnSchema(
                        name="email",
                        data_type="VARCHAR(320)",
                        regex_pattern=r"^[^@]+@[^@]+$",
                    ),
                ],
            )
        ],
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


async def test_is_metric_survives_persist_and_reload(session: AsyncSession) -> None:
    user = User(email="owner@example.com", hashed_password=hash_password("pw"))
    session.add(user)
    await session.flush()
    workspace = Workspace(name="ws")
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER"
        )
    )
    await session.flush()

    engine = SynthesisEngine(session, _StubGateway(_model()))
    resp = await engine.synthesize(
        SynthesizeRequest(
            source_type="natural_language",  # type: ignore[arg-type]
            content="reviews",
            target_paradigm="KIMBALL",  # type: ignore[arg-type]
            dialect="postgres",
            workspace_id=workspace.workspace_id,
        )
    )

    # Reload from the DB — the declared measure must round-trip.
    reloaded = await engine.get_model(resp.model_id)
    assert reloaded is not None
    rating = next(
        c
        for e in reloaded.entities
        for c in e.columns
        if c.name == "rating"
    )
    assert rating.is_metric is True
    assert rating.aggregation == "AVG"

    # Entity grain + governance metadata also round-trip (Sprint U2).
    fact = next(e for e in reloaded.entities if e.entity_name == "fact_reviews")
    assert fact.grain == "per review"
    assert fact.tier == "TIER_1_CRITICAL"
    assert fact.freshness_sla == "< 4h"

    # Column quality rules also round-trip (Sprint U3).
    stars = next(c for c in fact.columns if c.name == "stars")
    assert stars.min_value == 1
    assert stars.max_value == 5
    email = next(c for c in fact.columns if c.name == "email")
    assert email.regex_pattern == r"^[^@]+@[^@]+$"
