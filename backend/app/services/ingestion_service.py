"""Wikipedia article ingestion service."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients import (
    MediaWikiClient,
    WikipediaArticleData,
)
from backend.app.db.models import Article, ArticleCategory
from backend.app.db.repositories import (
    ArticleCategoryRepository,
    ArticleLinkRepository,
    ArticleRepository,
    CategoryRepository,
)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Represent one completed category ingestion."""

    articles: tuple[Article, ...]
    article_links: int


class IngestionService:
    """Coordinate Wikipedia retrieval, snapshots, and persistence."""

    def __init__(
        self,
        session: AsyncSession,
        mediawiki_client: MediaWikiClient,
        *,
        raw_data_directory: Path,
    ) -> None:
        """Initialize the ingestion service.

        Args:
            session: Active asynchronous database session.
            mediawiki_client: MediaWiki API client.
            raw_data_directory: Directory used for raw article snapshots.
        """
        self._session = session
        self._mediawiki_client = mediawiki_client
        self._raw_data_directory = raw_data_directory

        self._article_repository = ArticleRepository(session)
        self._article_link_repository = ArticleLinkRepository(session)
        self._category_repository = CategoryRepository(session)
        self._article_category_repository = ArticleCategoryRepository(session)

    async def ingest_category(
        self,
        category: str,
        *,
        limit: int,
        concurrency: int = 5,
    ) -> IngestionResult:
        """Ingest articles from a Wikipedia category.

        Args:
            category: Wikipedia category name.
            limit: Maximum number of articles to ingest.
            concurrency: Maximum number of concurrent HTTP requests.

        Returns:
            Successfully persisted articles.
        """
        page_ids = await self._mediawiki_client.get_category_page_ids(
            category,
            limit=limit,
        )

        article_data_collection = await self._mediawiki_client.get_articles(
            page_ids,
            concurrency=concurrency,
        )

        ingested_articles: list[Article] = []

        for article_data in article_data_collection:
            article = await self._ingest_article(article_data)
            ingested_articles.append(article)

        article_link_count = await self._ingest_article_links(
            ingested_articles,
            concurrency=concurrency,
        )

        return IngestionResult(
            articles=tuple(ingested_articles),
            article_links=article_link_count,
        )

    async def _ingest_article(
        self,
        article_data: WikipediaArticleData,
    ) -> Article:
        """Persist one Wikipedia article and its categories.

        Args:
            article_data: Article retrieved from MediaWiki.

        Returns:
            Persisted article.
        """
        existing_article = await self._article_repository.get_by_wikipedia_page_id(
            article_data.page_id
        )

        if existing_article is not None:
            return existing_article

        await self._save_raw_snapshot(article_data)

        article = Article(
            wikipedia_page_id=article_data.page_id,
            revision_id=article_data.revision_id,
            title=article_data.title,
            url=article_data.url,
            summary=article_data.summary,
            content=article_data.content,
            word_count=len(article_data.content.split()),
        )

        await self._article_repository.add(article)

        for category_name in article_data.categories:
            category = await self._category_repository.get_or_create(category_name)

            association = ArticleCategory(
                article_id=article.id,
                category_id=category.id,
            )

            await self._article_category_repository.add(association)

        return article

    async def _ingest_article_links(
        self,
        articles: list[Article],
        *,
        concurrency: int,
    ) -> int:
        """Persist links between articles present in the local corpus.

        Wikipedia links pointing outside the current MVF corpus are
        intentionally ignored. The resulting table therefore represents
        the directed subgraph induced by locally ingested articles.

        Args:
            articles: Locally ingested articles.
            concurrency: Maximum concurrent MediaWiki requests.

        Returns:
            Number of persisted directed article links.
        """
        if not articles:
            return 0

        page_ids = [article.wikipedia_page_id for article in articles]

        links_by_page_id = await self._mediawiki_client.get_article_links(
            page_ids,
            concurrency=concurrency,
        )

        all_linked_titles = {
            title for titles in links_by_page_id.values() for title in titles
        }

        target_articles = await self._article_repository.get_by_titles(
            all_linked_titles
        )

        target_by_title = {article.title: article for article in target_articles}

        source_by_page_id = {article.wikipedia_page_id: article for article in articles}

        persisted_count = 0

        for page_id, linked_titles in links_by_page_id.items():
            source_article = source_by_page_id[page_id]

            target_ids = {
                target_by_title[title].id
                for title in linked_titles
                if title in target_by_title
            }

            target_ids.discard(source_article.id)

            await self._article_link_repository.replace_outgoing(
                source_article_id=source_article.id,
                target_article_ids=target_ids,
            )

            persisted_count += len(target_ids)

        return persisted_count

    async def _save_raw_snapshot(
        self,
        article_data: WikipediaArticleData,
    ) -> None:
        """Persist an immutable raw Wikipedia snapshot as JSON.

        Args:
            article_data: Article data to serialize.
        """
        self._raw_data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = self._raw_data_directory / f"{article_data.page_id}.json"

        payload = json.dumps(
            asdict(article_data),
            ensure_ascii=False,
            indent=2,
        )

        await asyncio.to_thread(
            path.write_text,
            payload,
            encoding="utf-8",
        )
