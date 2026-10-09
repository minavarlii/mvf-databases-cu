"""FastAPI application dependencies."""

from __future__ import annotations

from typing import cast

from fastapi import HTTPException, Request, status

from backend.app.services import (
    EmbeddingService,
    TextGenerator,
)


def get_embedding_service(
    request: Request,
) -> EmbeddingService:
    """Return the application-wide embedding service.

    Args:
        request: Current FastAPI request.

    Returns:
        Shared embedding service.
    """
    return cast(
        EmbeddingService,
        request.app.state.embedding_service,
    )


def get_text_generator(
    request: Request,
) -> TextGenerator:
    """Return the configured application text generator.

    Args:
        request: Current FastAPI request.

    Returns:
        Shared text generator.

    Raises:
        HTTPException: If generation is not configured.
    """
    generator = getattr(
        request.app.state,
        "text_generator",
        None,
    )

    if generator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "RAG generation is unavailable because no LLM provider is configured."
            ),
        )

    return cast(
        TextGenerator,
        generator,
    )
