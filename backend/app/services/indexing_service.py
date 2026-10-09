"""Article chunking and embedding indexing service."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    Article,
    Chunk,
)
from backend.app.db.queries import (
    VectorQueries,
)
from backend.app.db.repositories.chunk_repository import (
    ChunkRepository,
)
from backend.app.services.chunking_service import (
    ChunkingService,
    TextChunk,
)
from backend.app.services.embedding_service import (
    EmbeddingService,
)

IndexingStatus = Literal[
    "indexed",
    "rebuilt",
    "skipped",
    "empty",
    "cleared",
]


@dataclass(frozen=True, slots=True)
class IndexingResult:
    """Represent the indexing outcome for one article."""

    article_id: int
    article_title: str
    status: IndexingStatus
    chunk_count: int


class IndexingService:
    """Create and maintain vector indexes for stored articles."""

    def __init__(
        self,
        session: AsyncSession,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
    ) -> None:
        """Initialize the indexing service.

        Args:
            session: Active asynchronous database session.
            chunking_service: Service used to split article text.
            embedding_service: Service used to generate embeddings.
        """
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._chunk_repository = ChunkRepository(session)
        self._vector_queries = VectorQueries(session)

    async def index_article(
        self,
        article: Article,
        *,
        force: bool = False,
    ) -> IndexingResult:
        """Ensure one article has a valid vector index.

        Existing chunks are compared with chunks generated from the
        current article content. Correctly indexed articles are skipped
        unless ``force`` is enabled. Missing or inconsistent indexes are
        rebuilt atomically within the caller's transaction.

        Args:
            article: Article to process.
            force: Rebuild the article even if existing chunks match.

        Returns:
            Indexing outcome for the article.
        """
        expected_chunks = self._chunking_service.chunk(article.content)

        existing_chunks = tuple(
            await self._chunk_repository.get_by_article_id(article.id)
        )

        if not expected_chunks:
            return await self._handle_empty_article(
                article=article,
                existing_chunks=existing_chunks,
            )

        if not force and self._chunks_match(
            existing_chunks,
            expected_chunks,
        ):
            return IndexingResult(
                article_id=article.id,
                article_title=article.title,
                status="skipped",
                chunk_count=len(existing_chunks),
            )

        embeddings = await self._embedding_service.embed_many(
            [chunk.content for chunk in expected_chunks]
        )

        had_existing_chunks = bool(existing_chunks)

        await self._chunk_repository.delete_by_article_id(article.id)

        for chunk, embedding in zip(
            expected_chunks,
            embeddings,
            strict=True,
        ):
            await self._vector_queries.insert_chunk(
                article_id=article.id,
                chunk_index=chunk.index,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding=embedding,
            )

        return IndexingResult(
            article_id=article.id,
            article_title=article.title,
            status=("rebuilt" if had_existing_chunks else "indexed"),
            chunk_count=len(expected_chunks),
        )

    async def _handle_empty_article(
        self,
        *,
        article: Article,
        existing_chunks: Sequence[Chunk],
    ) -> IndexingResult:
        """Handle an article whose current content produces no chunks."""
        if existing_chunks:
            await self._chunk_repository.delete_by_article_id(article.id)

            return IndexingResult(
                article_id=article.id,
                article_title=article.title,
                status="cleared",
                chunk_count=0,
            )

        return IndexingResult(
            article_id=article.id,
            article_title=article.title,
            status="empty",
            chunk_count=0,
        )

    @staticmethod
    def _chunks_match(
        existing_chunks: Sequence[Chunk],
        expected_chunks: Sequence[TextChunk],
    ) -> bool:
        """Check whether persisted chunks match current chunking output.

        Args:
            existing_chunks: Chunks currently stored in MariaDB.
            expected_chunks: Chunks generated from current article text.

        Returns:
            ``True`` when stored chunks exactly match the expected
            deterministic chunking output.
        """
        if len(existing_chunks) != len(expected_chunks):
            return False

        return all(
            existing.chunk_index == expected.index
            and existing.content == expected.content
            and existing.token_count == expected.token_count
            for existing, expected in zip(
                existing_chunks,
                expected_chunks,
                strict=True,
            )
        )
