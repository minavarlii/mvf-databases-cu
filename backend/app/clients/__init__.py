"""External API clients."""

from backend.app.clients.mediawiki import (
    MediaWikiClient,
    WikipediaArticleData,
)

__all__ = [
    "MediaWikiClient",
    "WikipediaArticleData",
]
