"""Async database engine, session factory, and FastAPI session dependency.

Provides a lazily-constructed SQLAlchemy 2.0 async engine bound to the
PostgreSQL 16 metadata store, an ``async_sessionmaker``, and a
``get_db_session`` dependency that yields a transactional
:class:`AsyncSession` per request.

The engine is created on first use (not at import) so that importing the app —
e.g. under test with the DB dependency overridden — does not require the
database driver to be installed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    return create_async_engine(
        str(settings.database_url),
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional async session.

    Commits on success, rolls back on any exception, and always closes.
    Declared with ``scope="function"`` (``SessionDep``), so the commit, or its
    failure, happens before the response is sent.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_streaming_db_session() -> AsyncGenerator[AsyncSession, None]:
    """A read-only session that stays open while a response streams.

    For the routes that read from the database as they send their body, the
    JSONL audit exports. Declared with ``scope="request"`` (see
    ``StreamingSessionDep``) so it outlives the handler; it never commits, and
    anything written through it is rolled back.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def dispose_engine() -> None:
    """Dispose of the engine's connection pool if it was ever created."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
