"""MariaDB-specific query package."""

from backend.app.db.queries.vector import (
    ARTICLE_SEARCH_SQL,
    HYBRID_SEARCH_SQL,
    LINKED_SEARCH_SQL,
    SEMANTIC_SEARCH_SQL,
    ArticleSearchResult,
    QueryPlanRow,
    VectorQueries,
    VectorSearchResult,
)

__all__ = [
    "ARTICLE_SEARCH_SQL",
    "HYBRID_SEARCH_SQL",
    "LINKED_SEARCH_SQL",
    "SEMANTIC_SEARCH_SQL",
    "ArticleSearchResult",
    "QueryPlanRow",
    "VectorQueries",
    "VectorSearchResult",
]
