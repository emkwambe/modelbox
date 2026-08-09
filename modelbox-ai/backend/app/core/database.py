"""Async database engine, session factory, and FastAPI session dependency.

Provides the SQLAlchemy 2.0 async engine bound to the PostgreSQL 16 metadata
store, an ``async_sessionmaker``, and a ``get_db_session`` dependency that yields
a transactional :class:`AsyncSession` per request.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# The async engine is created once at import time and reused across the app.
engine: AsyncEngine = create_async_engine(
    str(settings.database_url),
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional async session.

    Commits on success, rolls back on any exception, and always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose of the engine's connection pool (call on app shutdown)."""
    await engine.dispose()
