"""Application API router."""

from fastapi import APIRouter

from backend.app.api.routes import (
    articles_router,
    categories_router,
    rag_router,
    search_router,
)

api_router = APIRouter(
    prefix="/api",
)

api_router.include_router(articles_router)

api_router.include_router(categories_router)

api_router.include_router(search_router)

api_router.include_router(rag_router)
