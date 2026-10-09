"""MariaDB-native vector-search API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import (
    get_embedding_service,
)
from backend.app.api.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    LinkedSearchRequest,
    LinkedSearchResponse,
    QueryDebugResponse,
    QueryPlanResponse,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)
from backend.app.db import get_db_session
from backend.app.db.queries import (
    VectorSearchResult,
)
from backend.app.services import (
    EmbeddingService,
    SearchDebugInfo,
    SearchService,
)

router = APIRouter(
    prefix="/search",
    tags=["search"],
)


def build_debug_response(
    debug: SearchDebugInfo,
) -> QueryDebugResponse:
    """Convert search execution metadata to an API response."""
    return QueryDebugResponse(
        sql=debug.sql,
        parameters=debug.parameters,
        embedding_ms=debug.embedding_ms,
        search_ms=debug.search_ms,
        explain_ms=debug.explain_ms,
        total_ms=debug.total_ms,
        execution_plan=[
            QueryPlanResponse(
                select_id=row.select_id,
                select_type=row.select_type,
                table=row.table,
                access_type=row.access_type,
                possible_keys=row.possible_keys,
                key=row.key,
                rows=row.rows,
                extra=row.extra,
            )
            for row in debug.execution_plan
        ],
    )


def build_search_results(
    results: list[VectorSearchResult],
) -> list[SearchResultResponse]:
    """Convert internal vector-search results to API schemas."""
    return [
        SearchResultResponse(
            chunk_id=result.chunk_id,
            article_id=result.article_id,
            article_title=result.article_title,
            chunk_index=result.chunk_index,
            content=result.content,
            token_count=result.token_count,
            distance=result.distance,
        )
        for result in results
    ]


@router.post(
    "",
    response_model=SearchResponse,
)
async def semantic_search(
    payload: SearchRequest,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
) -> SearchResponse:
    """Perform native MariaDB semantic vector search."""
    search_service = SearchService(
        session=session,
        embedding_service=embedding_service,
    )

    execution = await search_service.search_with_debug(
        payload.query,
        limit=payload.limit,
    )

    return SearchResponse(
        query=payload.query,
        results=build_search_results(list(execution.results)),
        debug=build_debug_response(execution.debug),
    )


@router.post(
    "/hybrid",
    response_model=HybridSearchResponse,
)
async def hybrid_search(
    payload: HybridSearchRequest,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
) -> HybridSearchResponse:
    """Perform vector search with a relational category filter."""
    search_service = SearchService(
        session=session,
        embedding_service=embedding_service,
    )

    execution = await search_service.hybrid_search_with_debug(
        payload.query,
        category=payload.category,
        limit=payload.limit,
    )

    return HybridSearchResponse(
        query=payload.query,
        category=payload.category,
        results=build_search_results(list(execution.results)),
        debug=build_debug_response(execution.debug),
    )


@router.post(
    "/linked",
    response_model=LinkedSearchResponse,
)
async def linked_search(
    payload: LinkedSearchRequest,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
) -> LinkedSearchResponse:
    """Search within articles linked from a source article."""
    search_service = SearchService(
        session=session,
        embedding_service=embedding_service,
    )

    execution = await search_service.linked_search_with_debug(
        payload.query,
        source_title=payload.source_title,
        limit=payload.limit,
    )

    return LinkedSearchResponse(
        query=payload.query,
        source_title=payload.source_title,
        results=build_search_results(list(execution.results)),
        debug=build_debug_response(execution.debug),
    )
