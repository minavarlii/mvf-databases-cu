"""Retrieval-Augmented Generation API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import (
    get_embedding_service,
    get_text_generator,
)
from backend.app.api.routes.search import (
    build_debug_response,
)
from backend.app.api.schemas import (
    RagRequest,
    RagResponse,
    RagSourceResponse,
)
from backend.app.db import get_db_session
from backend.app.services import (
    EmbeddingService,
    RagService,
    TextGenerator,
)

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
)


@router.post(
    "",
    response_model=RagResponse,
)
async def generate_rag_answer(
    payload: RagRequest,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
    generator: Annotated[
        TextGenerator,
        Depends(get_text_generator),
    ],
) -> RagResponse:
    """Generate a grounded answer from MariaDB context."""
    rag_service = RagService(
        session=session,
        embedding_service=embedding_service,
        generator=generator,
    )

    try:
        result = await rag_service.answer(
            payload.question,
            top_k=payload.top_k,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return RagResponse(
        question=result.question,
        answer=result.answer,
        sources=[
            RagSourceResponse(
                article_id=source.article_id,
                article_title=source.article_title,
                chunk_index=source.chunk_index,
                content=source.content,
                distance=source.distance,
            )
            for source in result.sources
        ],
        debug=build_debug_response(result.debug),
    )
