"""API request and response schemas."""

from __future__ import annotations

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class SearchRequest(BaseModel):
    """Represent a semantic-search request."""

    query: str = Field(
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
    )

    @field_validator("query")
    @classmethod
    def validate_query(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate a search query."""
        normalized = value.strip()

        if not normalized:
            raise ValueError("Query must not be empty.")

        return normalized


class HybridSearchRequest(BaseModel):
    """Represent a hybrid vector-search request."""

    query: str = Field(
        min_length=1,
        max_length=1000,
    )
    category: str = Field(
        min_length=1,
        max_length=255,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
    )

    @field_validator(
        "query",
        "category",
    )
    @classmethod
    def validate_non_empty_text(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate text fields."""
        normalized = value.strip()

        if not normalized:
            raise ValueError("Value must not be empty.")

        return normalized


class LinkedSearchRequest(BaseModel):
    """Represent a graph-constrained vector-search request."""

    query: str = Field(
        min_length=1,
        max_length=1000,
    )
    source_title: str = Field(
        min_length=1,
        max_length=512,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
    )

    @field_validator(
        "query",
        "source_title",
    )
    @classmethod
    def validate_non_empty_text(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate text fields."""
        normalized = value.strip()

        if not normalized:
            raise ValueError("Value must not be empty.")

        return normalized


class RagRequest(BaseModel):
    """Represent a RAG question request."""

    question: str = Field(
        min_length=1,
        max_length=2000,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    @field_validator("question")
    @classmethod
    def validate_question(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate a RAG question."""
        normalized = value.strip()

        if not normalized:
            raise ValueError("Question must not be empty.")

        return normalized


class SearchResultResponse(BaseModel):
    """Represent one vector-search result."""

    chunk_id: int
    article_id: int
    article_title: str
    chunk_index: int
    content: str
    token_count: int
    distance: float


class QueryPlanResponse(BaseModel):
    """Represent one MariaDB EXPLAIN row."""

    select_id: int
    select_type: str
    table: str
    access_type: str | None
    possible_keys: str | None
    key: str | None
    rows: int | None
    extra: str | None


class QueryDebugResponse(BaseModel):
    """Represent SQL and execution metadata."""

    sql: str
    parameters: dict[str, str | int]
    embedding_ms: float
    search_ms: float
    explain_ms: float
    total_ms: float
    execution_plan: list[QueryPlanResponse]


class SearchResponse(BaseModel):
    """Represent a semantic-search response."""

    query: str
    results: list[SearchResultResponse]
    debug: QueryDebugResponse


class HybridSearchResponse(BaseModel):
    """Represent a hybrid-search response."""

    query: str
    category: str
    results: list[SearchResultResponse]
    debug: QueryDebugResponse


class LinkedSearchResponse(BaseModel):
    """Represent a graph-constrained search response."""

    query: str
    source_title: str
    results: list[SearchResultResponse]
    debug: QueryDebugResponse


class RagSourceResponse(BaseModel):
    """Represent one source used by RAG."""

    article_id: int
    article_title: str
    chunk_index: int
    content: str
    distance: float


class RagResponse(BaseModel):
    """Represent a generated RAG answer."""

    question: str
    answer: str
    sources: list[RagSourceResponse]
    debug: QueryDebugResponse


class ArticleSummaryResponse(BaseModel):
    """Represent a compact article response."""

    id: int
    wikipedia_page_id: int
    title: str
    url: str
    summary: str | None
    word_count: int


class ArticleListResponse(BaseModel):
    """Represent a paginated article collection."""

    items: list[ArticleSummaryResponse]
    total: int
    limit: int
    offset: int


class ArticleDetailsResponse(BaseModel):
    """Represent complete article details."""

    id: int
    wikipedia_page_id: int
    revision_id: int
    title: str
    url: str
    summary: str | None
    content: str
    word_count: int
    categories: list[str]


class CategoryResponse(BaseModel):
    """Represent one article category."""

    id: int
    name: str
    article_count: int


class CategoryListResponse(BaseModel):
    """Represent the available categories."""

    items: list[CategoryResponse]


class StatsResponse(BaseModel):
    """Represent live application and database metadata."""

    article_count: int
    chunk_count: int
    embedding_model: str
    vector_dimensions: int
    mariadb_version: str
