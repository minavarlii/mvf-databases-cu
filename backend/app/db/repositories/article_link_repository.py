"""Repository for Wikipedia article-link persistence."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import ArticleLink


class ArticleLinkRepository:
    """Provide asynchronous persistence operations for article links."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def exists(
        self,
        source_article_id: int,
        target_article_id: int,
    ) -> bool:
        """Check whether a directed article link already exists.

        Args:
            source_article_id: Source article identifier.
            target_article_id: Target article identifier.

        Returns:
            ``True`` when the directed link exists.
        """
        statement = select(ArticleLink).where(
            ArticleLink.source_article_id == source_article_id,
            ArticleLink.target_article_id == target_article_id,
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none() is not None

    async def add(self, article_link: ArticleLink) -> ArticleLink:
        """Add an article link to the current transaction.

        Args:
            article_link: Directed article link to persist.

        Returns:
            Persisted article link.
        """
        self._session.add(article_link)
        await self._session.flush()

        return article_link

    async def add_many(
        self,
        article_links: Sequence[ArticleLink],
    ) -> None:
        """Add multiple article links to the current transaction.

        Args:
            article_links: Directed article links to persist.
        """
        self._session.add_all(article_links)
        await self._session.flush()

    async def get_outgoing(
        self,
        article_id: int,
    ) -> Sequence[ArticleLink]:
        """Return all outgoing links for an article.

        Args:
            article_id: Source article identifier.

        Returns:
            Sequence of outgoing article links.
        """
        statement = select(ArticleLink).where(
            ArticleLink.source_article_id == article_id
        )

        result = await self._session.execute(statement)

        return result.scalars().all()

    async def replace_outgoing(
        self,
        *,
        source_article_id: int,
        target_article_ids: set[int],
    ) -> None:
        """Replace all outgoing links for one article.

        Args:
            source_article_id: Source article identifier.
            target_article_ids: Target article identifiers.
        """
        await self._session.execute(
            delete(ArticleLink).where(
                ArticleLink.source_article_id == source_article_id
            )
        )

        links = [
            ArticleLink(
                source_article_id=source_article_id,
                target_article_id=target_article_id,
            )
            for target_article_id in sorted(target_article_ids)
            if target_article_id != source_article_id
        ]

        self._session.add_all(links)
