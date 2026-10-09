"""Repository for article persistence operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Article


class ArticleRepository:
    """Provide asynchronous persistence operations for articles."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def get_by_id(self, article_id: int) -> Article | None:
        """Return an article by its internal database identifier.

        Args:
            article_id: Internal article identifier.

        Returns:
            Matching article or ``None`` when it does not exist.
        """
        return await self._session.get(Article, article_id)

    async def get_by_wikipedia_page_id(
        self,
        wikipedia_page_id: int,
    ) -> Article | None:
        """Return an article by its Wikipedia page identifier.

        Args:
            wikipedia_page_id: Wikipedia page identifier.

        Returns:
            Matching article or ``None`` when it does not exist.
        """
        statement = select(Article).where(
            Article.wikipedia_page_id == wikipedia_page_id
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_titles(
        self,
        titles: set[str],
    ) -> list[Article]:
        """Return articles matching any supplied title.

        Args:
            titles: Article titles to resolve.

        Returns:
            Matching articles.
        """
        if not titles:
            return []

        result = await self._session.execute(
            select(Article).where(Article.title.in_(titles))
        )

        return list(result.scalars().all())

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Article]:
        """Return a paginated collection of articles.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            Sequence of articles ordered by identifier.
        """
        statement = select(Article).order_by(Article.id).offset(offset).limit(limit)

        result = await self._session.execute(statement)

        return result.scalars().all()

    async def add(self, article: Article) -> Article:
        """Add an article to the current transaction.

        Args:
            article: Article instance to persist.

        Returns:
            Persisted article with generated fields populated.
        """
        self._session.add(article)
        await self._session.flush()

        return article

    async def add_many(
        self,
        articles: Sequence[Article],
    ) -> None:
        """Add multiple articles to the current transaction.

        Args:
            articles: Articles to persist.
        """
        self._session.add_all(articles)
        await self._session.flush()

    async def delete(self, article: Article) -> None:
        """Delete an article from the current transaction.

        Args:
            article: Article instance to delete.
        """
        await self._session.delete(article)
        await self._session.flush()
