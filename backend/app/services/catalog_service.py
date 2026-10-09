"""Article and category catalog service."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    Article,
    ArticleCategory,
    Category,
)


@dataclass(frozen=True, slots=True)
class ArticleSummary:
    """Represent a compact article description."""

    id: int
    wikipedia_page_id: int
    title: str
    url: str
    summary: str | None
    word_count: int


@dataclass(frozen=True, slots=True)
class ArticleDetails:
    """Represent complete article metadata."""

    id: int
    wikipedia_page_id: int
    revision_id: int
    title: str
    url: str
    summary: str | None
    content: str
    word_count: int
    categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArticlePage:
    """Represent one paginated article result."""

    items: tuple[ArticleSummary, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class CategorySummary:
    """Represent one Wikipedia category."""

    id: int
    name: str
    article_count: int


class CatalogService:
    """Provide read-only article and category catalog operations."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Initialize the catalog service.

        Args:
            session: Active asynchronous database session.
        """
        self._session = session

    async def list_articles(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> ArticlePage:
        """Return a paginated article list.

        Args:
            limit: Maximum number of articles.
            offset: Number of articles to skip.

        Returns:
            Paginated article collection.

        Raises:
            ValueError: If pagination arguments are invalid.
        """
        if limit <= 0:
            raise ValueError("Limit must be greater than zero.")

        if offset < 0:
            raise ValueError("Offset cannot be negative.")

        total = await self._session.scalar(select(func.count(Article.id)))

        result = await self._session.execute(
            select(Article).order_by(Article.title.asc()).limit(limit).offset(offset)
        )

        articles = result.scalars().all()

        return ArticlePage(
            items=tuple(
                ArticleSummary(
                    id=article.id,
                    wikipedia_page_id=(article.wikipedia_page_id),
                    title=article.title,
                    url=article.url,
                    summary=article.summary,
                    word_count=article.word_count,
                )
                for article in articles
            ),
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    async def get_article(
        self,
        article_id: int,
    ) -> ArticleDetails | None:
        """Return one article with category metadata.

        Args:
            article_id: Internal article identifier.

        Returns:
            Article details, or None if it does not exist.
        """
        article = await self._session.scalar(
            select(Article).where(Article.id == article_id)
        )

        if article is None:
            return None

        category_result = await self._session.execute(
            select(Category.name)
            .join(
                ArticleCategory,
                ArticleCategory.category_id == Category.id,
            )
            .where(ArticleCategory.article_id == article_id)
            .order_by(Category.name.asc())
        )

        categories = tuple(category_result.scalars().all())

        return ArticleDetails(
            id=article.id,
            wikipedia_page_id=(article.wikipedia_page_id),
            revision_id=article.revision_id,
            title=article.title,
            url=article.url,
            summary=article.summary,
            content=article.content,
            word_count=article.word_count,
            categories=categories,
        )

    async def list_categories(
        self,
    ) -> list[CategorySummary]:
        """Return categories with article counts.

        Returns:
            Categories ordered alphabetically.
        """
        result = await self._session.execute(
            select(
                Category.id,
                Category.name,
                func.count(ArticleCategory.article_id).label("article_count"),
            )
            .outerjoin(
                ArticleCategory,
                ArticleCategory.category_id == Category.id,
            )
            .group_by(
                Category.id,
                Category.name,
            )
            .order_by(Category.name.asc())
        )

        return [
            CategorySummary(
                id=row.id,
                name=row.name,
                article_count=int(row.article_count),
            )
            for row in result
        ]
