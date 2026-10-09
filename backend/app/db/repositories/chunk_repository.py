"""Repository for article chunk persistence operations."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Chunk


class ChunkRepository:
    """Provide asynchronous persistence operations for article chunks."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Initialize the repository.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def get_by_id(
        self,
        chunk_id: int,
    ) -> Chunk | None:
        """Return a chunk by its database identifier.

        Args:
            chunk_id: Internal chunk identifier.

        Returns:
            Matching chunk or ``None``.
        """
        return await self._session.get(
            Chunk,
            chunk_id,
        )

    async def get_by_article_id(
        self,
        article_id: int,
    ) -> Sequence[Chunk]:
        """Return all chunks belonging to an article.

        Args:
            article_id: Parent article identifier.

        Returns:
            Article chunks ordered by their original position.
        """
        statement = (
            select(Chunk)
            .where(Chunk.article_id == article_id)
            .order_by(Chunk.chunk_index)
        )

        result = await self._session.execute(statement)

        return result.scalars().all()

    async def add(
        self,
        chunk: Chunk,
    ) -> Chunk:
        """Add a chunk to the current transaction.

        Args:
            chunk: Chunk instance to persist.

        Returns:
            Persisted chunk.
        """
        self._session.add(chunk)
        await self._session.flush()

        return chunk

    async def add_many(
        self,
        chunks: Sequence[Chunk],
    ) -> None:
        """Add multiple chunks to the current transaction.

        Args:
            chunks: Chunks to persist.
        """
        self._session.add_all(chunks)
        await self._session.flush()

    async def delete_by_article_id(
        self,
        article_id: int,
    ) -> None:
        """Delete all chunks belonging to an article.

        Args:
            article_id: Parent article identifier.
        """
        await self._session.execute(delete(Chunk).where(Chunk.article_id == article_id))
