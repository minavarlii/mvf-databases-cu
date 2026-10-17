"""Application statistics API route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import StatsResponse
from backend.app.core.constants import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
)
from backend.app.db import get_db_session

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
)


@router.get(
    "",
    response_model=StatsResponse,
)
async def get_stats(
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> StatsResponse:
    """Return live corpus, embedding, and MariaDB metadata."""
    article_count = await session.scalar(text("SELECT COUNT(*) FROM articles"))

    chunk_count = await session.scalar(text("SELECT COUNT(*) FROM chunks"))

    mariadb_version = await session.scalar(text("SELECT VERSION()"))

    return StatsResponse(
        article_count=int(article_count or 0),
        chunk_count=int(chunk_count or 0),
        embedding_model=EMBEDDING_MODEL_NAME,
        vector_dimensions=EMBEDDING_DIMENSIONS,
        mariadb_version=str(mariadb_version or "MariaDB"),
    )
