"""Application API routes."""

from backend.app.api.routes.articles import (
    router as articles_router,
)
from backend.app.api.routes.categories import (
    router as categories_router,
)
from backend.app.api.routes.rag import (
    router as rag_router,
)
from backend.app.api.routes.search import (
    router as search_router,
)

__all__ = [
    "articles_router",
    "categories_router",
    "rag_router",
    "search_router",
]
