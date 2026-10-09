"""MVF FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api import api_router
from backend.app.core import get_settings
from backend.app.db import database_manager
from backend.app.generators import OpenAIGenerator
from backend.app.services import EmbeddingService


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resources.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to the running application.
    """
    settings = get_settings()

    embedding_service = EmbeddingService()

    app.state.embedding_service = embedding_service

    text_generator: OpenAIGenerator | None = None

    if settings.openai_api_key.strip():
        text_generator = OpenAIGenerator(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    app.state.text_generator = text_generator

    async with database_manager.session() as session:
        await session.execute(text("SELECT 1"))

    try:
        yield
    finally:
        if text_generator is not None:
            await text_generator.close()

        await database_manager.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "MariaDB-native vector search and Retrieval-Augmented Generation API."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get(
    "/health",
    tags=["system"],
)
async def health() -> dict[str, str]:
    """Return application health status."""
    return {
        "status": "ok",
    }
