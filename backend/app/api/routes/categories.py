"""Category catalog API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import (
    CategoryListResponse,
    CategoryResponse,
)
from backend.app.db import get_db_session
from backend.app.services import CatalogService

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)


@router.get(
    "",
    response_model=CategoryListResponse,
)
async def list_categories(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> CategoryListResponse:
    """Return available Wikipedia categories."""
    service = CatalogService(session)

    categories = await service.list_categories()

    return CategoryListResponse(
        items=[
            CategoryResponse(
                id=category.id,
                name=category.name,
                article_count=(category.article_count),
            )
            for category in categories
        ],
    )
