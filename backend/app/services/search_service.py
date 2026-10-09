"""Semantic, hybrid, and graph-constrained search service."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.queries import (
    HYBRID_SEARCH_SQL,
    LINKED_SEARCH_SQL,
    SEMANTIC_SEARCH_SQL,
    QueryPlanRow,
    VectorQueries,
    VectorSearchResult,
)
from backend.app.services.embedding_service import (
    EmbeddingService,
)


@dataclass(frozen=True, slots=True)
class SearchDebugInfo:
    """Represent database execution details for a search."""

    sql: str
    parameters: dict[str, str | int]
    embedding_ms: float
    search_ms: float
    explain_ms: float
    total_ms: float
    execution_plan: tuple[QueryPlanRow, ...]


@dataclass(frozen=True, slots=True)
class SearchExecution:
    """Represent search results with execution metadata."""

    results: tuple[VectorSearchResult, ...]
    debug: SearchDebugInfo


class SearchService:
    """Provide MariaDB-native vector-search operations."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        embedding_service: EmbeddingService,
    ) -> None:
        """Initialize the search service.

        Args:
            session: Active asynchronous database session.
            embedding_service: Query embedding generator.
        """
        self._embedding_service = embedding_service
        self._vector_queries = VectorQueries(session)

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Perform semantic vector search.

        Args:
            query: Natural-language search query.
            limit: Maximum number of results.

        Returns:
            Ranked semantic-search results.

        Raises:
            ValueError: If query is empty.
        """
        normalized_query = self._normalize_query(query)

        embedding = await self._embedding_service.embed_text(normalized_query)

        return await self._vector_queries.semantic_search(
            embedding=embedding,
            limit=limit,
        )

    async def hybrid_search(
        self,
        query: str,
        *,
        category: str,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Perform semantic search within a category.

        Args:
            query: Natural-language search query.
            category: Wikipedia category filter.
            limit: Maximum number of results.

        Returns:
            Ranked hybrid-search results.

        Raises:
            ValueError: If query or category is empty.
        """
        normalized_query = self._normalize_query(query)
        normalized_category = self._normalize_required_text(
            category,
            field_name="Category",
        )

        embedding = await self._embedding_service.embed_text(normalized_query)

        return await self._vector_queries.hybrid_search(
            embedding=embedding,
            category=normalized_category,
            limit=limit,
        )

    async def linked_search(
        self,
        query: str,
        *,
        source_title: str,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Search within articles linked from one article.

        Args:
            query: Natural-language search query.
            source_title: Source Wikipedia article title.
            limit: Maximum number of results.

        Returns:
            Ranked graph-constrained vector-search results.

        Raises:
            ValueError: If query or source title is empty.
        """
        normalized_query = self._normalize_query(query)
        normalized_source_title = self._normalize_required_text(
            source_title,
            field_name="Source title",
        )

        embedding = await self._embedding_service.embed_text(normalized_query)

        return await self._vector_queries.linked_search(
            embedding=embedding,
            source_title=(normalized_source_title),
            limit=limit,
        )

    async def search_with_debug(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> SearchExecution:
        """Perform semantic search with execution metadata."""
        normalized_query = self._normalize_query(query)

        total_started = perf_counter()

        embedding_started = perf_counter()

        embedding = await self._embedding_service.embed_text(normalized_query)

        embedding_ms = self._elapsed_ms(embedding_started)

        search_started = perf_counter()

        results = await self._vector_queries.semantic_search(
            embedding=embedding,
            limit=limit,
        )

        search_ms = self._elapsed_ms(search_started)

        explain_started = perf_counter()

        plan = await self._vector_queries.explain_semantic_search(
            embedding=embedding,
            limit=limit,
        )

        explain_ms = self._elapsed_ms(explain_started)

        return SearchExecution(
            results=tuple(results),
            debug=SearchDebugInfo(
                sql=SEMANTIC_SEARCH_SQL,
                parameters={
                    "embedding": ("<384-dimensional query vector>"),
                    "limit": limit,
                },
                embedding_ms=embedding_ms,
                search_ms=search_ms,
                explain_ms=explain_ms,
                total_ms=self._elapsed_ms(total_started),
                execution_plan=tuple(plan),
            ),
        )

    async def hybrid_search_with_debug(
        self,
        query: str,
        *,
        category: str,
        limit: int = 5,
    ) -> SearchExecution:
        """Perform hybrid search with execution metadata."""
        normalized_query = self._normalize_query(query)
        normalized_category = self._normalize_required_text(
            category,
            field_name="Category",
        )

        total_started = perf_counter()

        embedding_started = perf_counter()

        embedding = await self._embedding_service.embed_text(normalized_query)

        embedding_ms = self._elapsed_ms(embedding_started)

        search_started = perf_counter()

        results = await self._vector_queries.hybrid_search(
            embedding=embedding,
            category=normalized_category,
            limit=limit,
        )

        search_ms = self._elapsed_ms(search_started)

        explain_started = perf_counter()

        plan = await self._vector_queries.explain_hybrid_search(
            embedding=embedding,
            category=normalized_category,
            limit=limit,
        )

        explain_ms = self._elapsed_ms(explain_started)

        return SearchExecution(
            results=tuple(results),
            debug=SearchDebugInfo(
                sql=HYBRID_SEARCH_SQL,
                parameters={
                    "embedding": ("<384-dimensional query vector>"),
                    "category": normalized_category,
                    "limit": limit,
                },
                embedding_ms=embedding_ms,
                search_ms=search_ms,
                explain_ms=explain_ms,
                total_ms=self._elapsed_ms(total_started),
                execution_plan=tuple(plan),
            ),
        )

    async def linked_search_with_debug(
        self,
        query: str,
        *,
        source_title: str,
        limit: int = 5,
    ) -> SearchExecution:
        """Perform graph-constrained search with debug metadata.

        Args:
            query: Natural-language search query.
            source_title: Source Wikipedia article title.
            limit: Maximum number of results.

        Returns:
            Search results with SQL, timings, and EXPLAIN plan.

        Raises:
            ValueError: If query or source title is empty.
        """
        normalized_query = self._normalize_query(query)
        normalized_source_title = self._normalize_required_text(
            source_title,
            field_name="Source title",
        )

        total_started = perf_counter()

        embedding_started = perf_counter()

        embedding = await self._embedding_service.embed_text(normalized_query)

        embedding_ms = self._elapsed_ms(embedding_started)

        search_started = perf_counter()

        results = await self._vector_queries.linked_search(
            embedding=embedding,
            source_title=(normalized_source_title),
            limit=limit,
        )

        search_ms = self._elapsed_ms(search_started)

        explain_started = perf_counter()

        plan = await self._vector_queries.explain_linked_search(
            embedding=embedding,
            source_title=(normalized_source_title),
            limit=limit,
        )

        explain_ms = self._elapsed_ms(explain_started)

        return SearchExecution(
            results=tuple(results),
            debug=SearchDebugInfo(
                sql=LINKED_SEARCH_SQL,
                parameters={
                    "embedding": ("<384-dimensional query vector>"),
                    "source_title": (normalized_source_title),
                    "limit": limit,
                },
                embedding_ms=embedding_ms,
                search_ms=search_ms,
                explain_ms=explain_ms,
                total_ms=self._elapsed_ms(total_started),
                execution_plan=tuple(plan),
            ),
        )

    @staticmethod
    def _normalize_query(
        query: str,
    ) -> str:
        """Normalize and validate a search query."""
        return SearchService._normalize_required_text(
            query,
            field_name="Search query",
        )

    @staticmethod
    def _normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Normalize and validate required text."""
        normalized = value.strip()

        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")

        return normalized

    @staticmethod
    def _elapsed_ms(
        started_at: float,
    ) -> float:
        """Return elapsed milliseconds from a timer."""
        return (perf_counter() - started_at) * 1000.0
