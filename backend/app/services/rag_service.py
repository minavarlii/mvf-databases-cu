"""Retrieval-Augmented Generation service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.queries import VectorSearchResult
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.search_service import (
    SearchDebugInfo,
    SearchService,
)


@dataclass(frozen=True, slots=True)
class RagSource:
    """Represent one source used to generate an answer."""

    article_id: int
    article_title: str
    chunk_index: int
    content: str
    distance: float


@dataclass(frozen=True, slots=True)
class RagResult:
    """Represent one completed RAG response."""

    question: str
    answer: str
    sources: tuple[RagSource, ...]
    debug: SearchDebugInfo


class TextGenerator(Protocol):
    """Define the interface required from an LLM generator."""

    async def generate(
        self,
        *,
        prompt: str,
    ) -> str:
        """Generate text from a prompt."""
        ...

    async def close(self) -> None:
        """Release generator resources."""
        ...


class RagService:
    """Coordinate retrieval and text generation."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        generator: TextGenerator,
    ) -> None:
        """Initialize the RAG service.

        Args:
            session: Active asynchronous database session.
            embedding_service: Query embedding service.
            generator: Text-generation implementation.
        """
        self._search_service = SearchService(
            session=session,
            embedding_service=embedding_service,
        )
        self._generator = generator

    async def answer(
        self,
        question: str,
        *,
        top_k: int = 5,
    ) -> RagResult:
        """Answer a question using retrieved MariaDB context.

        Args:
            question: User question.
            top_k: Number of chunks used as context.

        Returns:
            Generated answer with retrieval sources and debug data.

        Raises:
            ValueError: If question or top_k is invalid.
        """
        normalized_question = question.strip()

        if not normalized_question:
            raise ValueError("Question must not be empty.")

        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        execution = await self._search_service.search_with_debug(
            normalized_question,
            limit=top_k,
        )

        results = list(execution.results)

        prompt = self._build_prompt(
            question=normalized_question,
            results=results,
        )

        answer = await self._generator.generate(
            prompt=prompt,
        )

        sources = tuple(
            RagSource(
                article_id=result.article_id,
                article_title=result.article_title,
                chunk_index=result.chunk_index,
                content=result.content,
                distance=result.distance,
            )
            for result in results
        )

        return RagResult(
            question=normalized_question,
            answer=answer,
            sources=sources,
            debug=execution.debug,
        )

    @staticmethod
    def _build_prompt(
        *,
        question: str,
        results: list[VectorSearchResult],
    ) -> str:
        """Build a grounded RAG prompt.

        Args:
            question: User question.
            results: Retrieved database chunks.

        Returns:
            Prompt supplied to the text generator.
        """
        context_blocks: list[str] = []

        for index, result in enumerate(
            results,
            start=1,
        ):
            context_blocks.append(
                "\n".join(
                    [
                        f"[Source {index}]",
                        f"Article: {result.article_title}",
                        f"Chunk: {result.chunk_index}",
                        result.content,
                    ]
                )
            )

        context = "\n\n".join(context_blocks)

        return (
            "You are answering a question using only the "
            "retrieved context below.\n"
            "Do not invent facts that are not supported by "
            "the context.\n"
            "If the context is insufficient, explicitly say so.\n"
            "Cite supporting sources using [Source N].\n\n"
            f"Question:\n{question}\n\n"
            f"Context:\n{context}\n\n"
            "Answer:"
        )
