"""Repository for article-category associations."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ArticleCategory


class ArticleCategoryRepository:
    """Provide persistence operations for article-category associations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def add(
        self,
        association: ArticleCategory,
    ) -> ArticleCategory:
        """Add an article-category association.

        Args:
            association: Association to persist.

        Returns:
            Persisted association.
        """
        self._session.add(association)
        await self._session.flush()

        return association

    async def add_many(
        self,
        associations: Sequence[ArticleCategory],
    ) -> None:
        """Add multiple article-category associations.

        Args:
            associations: Associations to persist.
        """
        self._session.add_all(associations)
        await self._session.flush()
