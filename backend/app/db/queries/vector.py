"""MariaDB-native vector database operations."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

SEMANTIC_SEARCH_SQL = """
SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
ORDER BY distance ASC
LIMIT :limit
""".strip()


ARTICLE_SEARCH_SQL = """
SELECT
    a.id AS article_id,
    a.title AS article_title,
    MIN(
        VEC_DISTANCE_COSINE(
            c.embedding,
            VEC_FromText(:embedding)
        )
    ) AS distance
FROM articles AS a
INNER JOIN chunks AS c
    ON c.article_id = a.id
GROUP BY
    a.id,
    a.title
ORDER BY distance ASC
LIMIT :limit
""".strip()


HYBRID_SEARCH_SQL = """
SELECT
    c.id AS chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM chunks AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
INNER JOIN article_categories AS ac
    ON ac.article_id = a.id
INNER JOIN categories AS cat
    ON cat.id = ac.category_id
WHERE cat.name = :category
ORDER BY distance ASC
LIMIT :limit
""".strip()


LINKED_SEARCH_SQL = """
SELECT
    c.id AS chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = :source_title
ORDER BY distance ASC
LIMIT :limit
""".strip()


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """Represent one semantic vector-search result."""

    chunk_id: int
    article_id: int
    article_title: str
    chunk_index: int
    content: str
    token_count: int
    distance: float


@dataclass(frozen=True, slots=True)
class ArticleSearchResult:
    """Represent one exact article-level semantic-search result."""

    article_id: int
    article_title: str
    distance: float


@dataclass(frozen=True, slots=True)
class QueryPlanRow:
    """Represent one row from a MariaDB EXPLAIN plan."""

    select_id: int
    select_type: str
    table: str
    access_type: str | None
    possible_keys: str | None
    key: str | None
    rows: int | None
    extra: str | None


class VectorQueries:
    """Execute MariaDB-specific native vector operations."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Initialize vector queries.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def insert_chunk(
        self,
        *,
        article_id: int,
        chunk_index: int,
        content: str,
        token_count: int,
        embedding: list[float],
    ) -> None:
        """Insert a chunk with its native MariaDB vector.

        Args:
            article_id: Parent article identifier.
            chunk_index: Position of the chunk inside the article.
            content: Chunk text.
            token_count: Number of embedding-model tokens.
            embedding: Dense embedding vector.
        """
        embedding_json = self._serialize_embedding(embedding)

        await self._session.execute(
            text(
                """
                INSERT INTO chunks (
                    article_id,
                    chunk_index,
                    content,
                    token_count,
                    embedding
                )
                VALUES (
                    :article_id,
                    :chunk_index,
                    :content,
                    :token_count,
                    VEC_FromText(:embedding)
                )
                """
            ),
            {
                "article_id": article_id,
                "chunk_index": chunk_index,
                "content": content,
                "token_count": token_count,
                "embedding": embedding_json,
            },
        )

    async def semantic_search(
        self,
        *,
        embedding: list[float],
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Find chunks nearest to a query embedding.

        Args:
            embedding: Query embedding.
            limit: Maximum number of results.

        Returns:
            Chunks ordered from most to least semantically similar.

        Raises:
            ValueError: If limit is invalid.
        """
        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(SEMANTIC_SEARCH_SQL),
            {
                "embedding": embedding_json,
                "limit": limit,
            },
        )

        return [self._build_vector_search_result(row) for row in result.mappings()]

    async def article_search(
        self,
        *,
        embedding: list[float],
        limit: int = 10,
    ) -> list[ArticleSearchResult]:
        """Rank articles by their nearest chunk.

        The score for each article is the minimum cosine distance
        between the query embedding and any chunk belonging to that
        article.

        This query is primarily intended as an exact article-level
        evaluation oracle rather than the production chunk-search
        path.

        Args:
            embedding: Query embedding.
            limit: Maximum number of articles.

        Returns:
            Articles ordered from most to least semantically similar.

        Raises:
            ValueError: If limit is invalid.
        """
        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(ARTICLE_SEARCH_SQL),
            {
                "embedding": embedding_json,
                "limit": limit,
            },
        )

        return [self._build_article_search_result(row) for row in result.mappings()]

    async def hybrid_search(
        self,
        *,
        embedding: list[float],
        category: str,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Search semantically within a Wikipedia category.

        Args:
            embedding: Query embedding.
            category: Wikipedia category used as a relational filter.
            limit: Maximum number of results.

        Returns:
            Matching chunks ordered by cosine distance.

        Raises:
            ValueError: If category is empty or limit is invalid.
        """
        normalized_category = category.strip()

        if not normalized_category:
            raise ValueError("Category must not be empty.")

        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(HYBRID_SEARCH_SQL),
            {
                "embedding": embedding_json,
                "category": normalized_category,
                "limit": limit,
            },
        )

        return [self._build_vector_search_result(row) for row in result.mappings()]

    async def linked_search(
        self,
        *,
        embedding: list[float],
        source_title: str,
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Search chunks from articles linked by one source article.

        Args:
            embedding: Query embedding.
            source_title: Source Wikipedia article title.
            limit: Maximum number of results.

        Returns:
            Graph-constrained vector-search results.

        Raises:
            ValueError: If source title is empty or limit is invalid.
        """
        normalized_source_title = source_title.strip()

        if not normalized_source_title:
            raise ValueError("Source title must not be empty.")

        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(LINKED_SEARCH_SQL),
            {
                "embedding": embedding_json,
                "source_title": (normalized_source_title),
                "limit": limit,
            },
        )

        return [self._build_vector_search_result(row) for row in result.mappings()]

    async def explain_semantic_search(
        self,
        *,
        embedding: list[float],
        limit: int = 5,
    ) -> list[QueryPlanRow]:
        """Explain a semantic vector-search query.

        Args:
            embedding: Query embedding.
            limit: Maximum number of results.

        Returns:
            MariaDB execution-plan rows.

        Raises:
            ValueError: If limit is invalid.
        """
        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(f"EXPLAIN {SEMANTIC_SEARCH_SQL}"),
            {
                "embedding": embedding_json,
                "limit": limit,
            },
        )

        return [self._build_query_plan_row(row) for row in result.mappings()]

    async def explain_hybrid_search(
        self,
        *,
        embedding: list[float],
        category: str,
        limit: int = 5,
    ) -> list[QueryPlanRow]:
        """Explain a relationally filtered vector-search query.

        Args:
            embedding: Query embedding.
            category: Wikipedia category filter.
            limit: Maximum number of results.

        Returns:
            MariaDB execution-plan rows.

        Raises:
            ValueError: If category is empty or limit is invalid.
        """
        normalized_category = category.strip()

        if not normalized_category:
            raise ValueError("Category must not be empty.")

        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(f"EXPLAIN {HYBRID_SEARCH_SQL}"),
            {
                "embedding": embedding_json,
                "category": normalized_category,
                "limit": limit,
            },
        )

        return [self._build_query_plan_row(row) for row in result.mappings()]

    async def explain_linked_search(
        self,
        *,
        embedding: list[float],
        source_title: str,
        limit: int = 5,
    ) -> list[QueryPlanRow]:
        """Explain a graph-constrained vector-search query.

        Args:
            embedding: Query embedding.
            source_title: Source Wikipedia article title.
            limit: Maximum number of results.

        Returns:
            MariaDB execution-plan rows.

        Raises:
            ValueError: If source title is empty or limit is invalid.
        """
        normalized_source_title = source_title.strip()

        if not normalized_source_title:
            raise ValueError("Source title must not be empty.")

        self._validate_limit(limit)

        embedding_json = self._serialize_embedding(embedding)

        result = await self._session.execute(
            text(f"EXPLAIN {LINKED_SEARCH_SQL}"),
            {
                "embedding": embedding_json,
                "source_title": (normalized_source_title),
                "limit": limit,
            },
        )

        return [self._build_query_plan_row(row) for row in result.mappings()]

    @staticmethod
    def _validate_limit(
        limit: int,
    ) -> None:
        """Validate a search result limit.

        Args:
            limit: Requested result count.

        Raises:
            ValueError: If limit is not positive.
        """
        if limit <= 0:
            raise ValueError("Search limit must be greater than zero.")

    @staticmethod
    def _serialize_embedding(
        embedding: list[float],
    ) -> str:
        """Serialize an embedding for MariaDB VEC_FromText.

        Args:
            embedding: Dense floating-point vector.

        Returns:
            Compact JSON representation of the vector.
        """
        return json.dumps(
            embedding,
            separators=(
                ",",
                ":",
            ),
        )

    @staticmethod
    def _parse_distance(
        distance: object,
    ) -> float:
        """Convert a MariaDB vector distance to float.

        Args:
            distance: Raw distance value returned by MariaDB.

        Returns:
            Floating-point vector distance.

        Raises:
            RuntimeError: If MariaDB unexpectedly returns NULL.
            ValueError: If the returned value cannot be converted.
        """
        if distance is None:
            raise RuntimeError("MariaDB returned NULL for vector distance.")

        return float(str(distance))

    @classmethod
    def _build_vector_search_result(
        cls,
        row: RowMapping,
    ) -> VectorSearchResult:
        """Build one structured vector-search result.

        Args:
            row: SQLAlchemy row mapping.

        Returns:
            Structured chunk-level search result.
        """
        return VectorSearchResult(
            chunk_id=int(row["chunk_id"]),
            article_id=int(row["article_id"]),
            article_title=str(row["article_title"]),
            chunk_index=int(row["chunk_index"]),
            content=str(row["content"]),
            token_count=int(row["token_count"]),
            distance=cls._parse_distance(row["distance"]),
        )

    @classmethod
    def _build_article_search_result(
        cls,
        row: RowMapping,
    ) -> ArticleSearchResult:
        """Build one structured article-level search result.

        Args:
            row: SQLAlchemy row mapping.

        Returns:
            Structured article-level search result.
        """
        return ArticleSearchResult(
            article_id=int(row["article_id"]),
            article_title=str(row["article_title"]),
            distance=cls._parse_distance(row["distance"]),
        )

    @staticmethod
    def _build_query_plan_row(
        row: RowMapping,
    ) -> QueryPlanRow:
        """Build a structured query-plan row.

        Args:
            row: SQLAlchemy row mapping returned by MariaDB EXPLAIN.

        Returns:
            Structured execution-plan row.
        """
        return QueryPlanRow(
            select_id=int(row["id"]),
            select_type=str(row["select_type"]),
            table=str(row["table"]),
            access_type=(str(row["type"]) if row["type"] is not None else None),
            possible_keys=(
                str(row["possible_keys"]) if row["possible_keys"] is not None else None
            ),
            key=(str(row["key"]) if row["key"] is not None else None),
            rows=(int(row["rows"]) if row["rows"] is not None else None),
            extra=(str(row["Extra"]) if row["Extra"] is not None else None),
        )
