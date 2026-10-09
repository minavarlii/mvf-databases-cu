"""Article catalog API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import (
    ArticleDetailsResponse,
    ArticleListResponse,
    ArticleSummaryResponse,
)
from backend.app.db import get_db_session
from backend.app.services import CatalogService

router = APIRouter(
    prefix="/articles",
    tags=["articles"],
)


@router.get(
    "",
    response_model=ArticleListResponse,
)
async def list_articles(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,
    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
) -> ArticleListResponse:
    """Return paginated Wikipedia articles."""
    service = CatalogService(session)

    page = await service.list_articles(
        limit=limit,
        offset=offset,
    )

    return ArticleListResponse(
        items=[
            ArticleSummaryResponse(
                id=article.id,
                wikipedia_page_id=(article.wikipedia_page_id),
                title=article.title,
                url=article.url,
                summary=article.summary,
                word_count=article.word_count,
            )
            for article in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{article_id}",
    response_model=ArticleDetailsResponse,
)
async def get_article(
    article_id: int,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> ArticleDetailsResponse:
    """Return one article by internal identifier."""
    service = CatalogService(session)

    article = await service.get_article(article_id)

    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found.",
        )

    return ArticleDetailsResponse(
        id=article.id,
        wikipedia_page_id=(article.wikipedia_page_id),
        revision_id=article.revision_id,
        title=article.title,
        url=article.url,
        summary=article.summary,
        content=article.content,
        word_count=article.word_count,
        categories=list(article.categories),
    )
