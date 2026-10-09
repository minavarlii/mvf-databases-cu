"""Asynchronous database session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core import get_settings


class DatabaseSessionManager:
    """Manage the asynchronous SQLAlchemy engine and sessions."""

    def __init__(self, database_url: str) -> None:
        """Initialize the database engine and session factory.

        Args:
            database_url: SQLAlchemy-compatible asynchronous database URL.
        """
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the asynchronous SQLAlchemy engine."""
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional asynchronous database session.

        Yields:
            AsyncSession: Active SQLAlchemy asynchronous session.
        """
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def dispose(self) -> None:
        """Dispose of the database connection pool."""
        await self._engine.dispose()


settings = get_settings()

database_manager = DatabaseSessionManager(
    database_url=settings.database_url,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for FastAPI dependencies.

    Yields:
        AsyncSession: Active asynchronous database session.
    """
    async with database_manager.session() as session:
        yield session
