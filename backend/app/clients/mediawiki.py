"""Asynchronous MediaWiki API client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True, slots=True)
class WikipediaArticleData:
    """Represent article data returned by the MediaWiki API."""

    page_id: int
    revision_id: int
    title: str
    url: str
    summary: str | None
    content: str
    categories: tuple[str, ...]


class MediaWikiClient:
    """Provide asynchronous access to the MediaWiki API."""

    BASE_URL = "https://en.wikipedia.org"
    API_PATH = "/w/api.php"
    ARTICLE_BASE_URL = "https://en.wikipedia.org/wiki/"
    MAX_RETRIES = 5
    RETRYABLE_STATUS_CODES = {
        429,
        500,
        502,
        503,
        504,
    }

    def __init__(
        self,
        *,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the MediaWiki client.

        Args:
            timeout: Maximum HTTP request duration in seconds.
        """
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "MVF/0.1 "
                    "(Constructor University database project; "
                    "vismayilov@constructor.university) "
                    f"httpx/{httpx.__version__}"
                ),
                "Accept": "application/json",
            },
        )

    async def __aenter__(self) -> MediaWikiClient:
        """Enter the asynchronous client context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Close the underlying HTTP client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _get(
        self,
        *,
        params: dict[str, str | int],
    ) -> httpx.Response:
        """Perform a resilient MediaWiki GET request.

        Args:
            params: MediaWiki API query parameters.

        Returns:
            Successful HTTP response.

        Raises:
            httpx.HTTPStatusError: If all retry attempts fail.
        """
        for attempt in range(self.MAX_RETRIES):
            response = await self._client.get(
                self.API_PATH,
                params=params,
            )

            if response.status_code not in self.RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response

            if attempt == self.MAX_RETRIES - 1:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")

            delay = float(retry_after) if retry_after is not None else 2.0**attempt

            await asyncio.sleep(delay)

        raise RuntimeError("Unreachable MediaWiki retry state.")

    async def get_category_page_ids(
        self,
        category: str,
        *,
        limit: int,
    ) -> list[int]:
        """Return article page identifiers from a Wikipedia category.

        Args:
            category: Wikipedia category name without the ``Category:`` prefix.
            limit: Maximum number of article identifiers to return.

        Returns:
            Wikipedia page identifiers belonging to the category.

        Raises:
            ValueError: If limit is not positive.
            httpx.HTTPStatusError: If the MediaWiki request fails.
        """
        if limit <= 0:
            raise ValueError("Limit must be greater than zero.")

        page_ids: list[int] = []
        continuation: str | None = None

        while len(page_ids) < limit:
            remaining = limit - len(page_ids)

            params: dict[str, str | int] = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmnamespace": 0,
                "cmlimit": min(remaining, 500),
            }

            if continuation is not None:
                params["cmcontinue"] = continuation

            response = await self._get(params=params)

            payload: dict[str, Any] = response.json()

            members = payload.get("query", {}).get(
                "categorymembers",
                [],
            )

            page_ids.extend(
                int(member["pageid"]) for member in members if "pageid" in member
            )

            continuation = payload.get(
                "continue",
                {},
            ).get("cmcontinue")

            if continuation is None:
                break

        return page_ids[:limit]

    async def get_article(
        self,
        page_id: int,
    ) -> WikipediaArticleData:
        """Fetch a complete Wikipedia article.

        Args:
            page_id: Wikipedia page identifier.

        Returns:
            Structured article data.

        Raises:
            ValueError: If the requested page cannot be found.
            httpx.HTTPStatusError: If the MediaWiki request fails.
        """
        params: dict[str, str | int] = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "pageids": page_id,
            "prop": "extracts|categories|revisions",
            "explaintext": 1,
            "exsectionformat": "plain",
            "cllimit": "max",
            "rvprop": "ids",
            "redirects": 1,
        }

        response = await self._get(params=params)

        payload: dict[str, Any] = response.json()

        pages = payload.get("query", {}).get("pages", [])

        if not pages or pages[0].get("missing"):
            raise ValueError(f"Wikipedia page {page_id} was not found.")

        page = pages[0]

        title = str(page["title"])
        content = str(page.get("extract", "")).strip()

        categories = tuple(
            self._normalize_category_name(category["title"])
            for category in page.get("categories", [])
            if "title" in category
        )

        revisions = page.get("revisions", [])
        revision_id = int(revisions[0]["revid"]) if revisions else 0

        return WikipediaArticleData(
            page_id=int(page["pageid"]),
            revision_id=revision_id,
            title=title,
            url=self._build_article_url(title),
            summary=self._extract_summary(content),
            content=content,
            categories=categories,
        )

    async def get_articles(
        self,
        page_ids: list[int],
        *,
        concurrency: int = 5,
    ) -> list[WikipediaArticleData]:
        """Fetch multiple Wikipedia articles concurrently.

        Args:
            page_ids: Wikipedia page identifiers.
            concurrency: Maximum number of concurrent HTTP requests.

        Returns:
            Articles in the same order as the supplied identifiers.

        Raises:
            ValueError: If concurrency is not positive.
        """
        if concurrency <= 0:
            raise ValueError("Concurrency must be greater than zero.")

        semaphore = asyncio.Semaphore(concurrency)

        async def fetch(
            page_id: int,
        ) -> WikipediaArticleData:
            async with semaphore:
                return await self.get_article(page_id)

        return list(await asyncio.gather(*(fetch(page_id) for page_id in page_ids)))

    async def get_article_link_titles(
        self,
        page_id: int,
    ) -> tuple[str, ...]:
        """Return outgoing Wikipedia article links for one page.

        Only links to main-namespace Wikipedia articles are returned.

        Args:
            page_id: Wikipedia page identifier.

        Returns:
            Unique outgoing article titles in deterministic order.
        """
        titles: set[str] = set()
        continuation: str | None = None

        while True:
            params: dict[str, str | int] = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "pageids": page_id,
                "prop": "links",
                "plnamespace": 0,
                "pllimit": "max",
            }

            if continuation is not None:
                params["plcontinue"] = continuation

            response = await self._get(params=params)

            payload = response.json()

            pages = payload.get(
                "query",
                {},
            ).get(
                "pages",
                [],
            )

            if not pages:
                break

            links = pages[0].get(
                "links",
                [],
            )

            for link in links:
                title = str(
                    link.get(
                        "title",
                        "",
                    )
                ).strip()

                if title:
                    titles.add(title)

            continuation_payload = payload.get("continue")

            if not continuation_payload:
                break

            continuation = continuation_payload.get("plcontinue")

            if not continuation:
                break

        return tuple(sorted(titles))

    async def get_article_links(
        self,
        page_ids: list[int],
        *,
        concurrency: int = 5,
    ) -> dict[int, tuple[str, ...]]:
        """Fetch outgoing links for multiple Wikipedia pages.

        Args:
            page_ids: Wikipedia page identifiers.
            concurrency: Maximum simultaneous API requests.

        Returns:
            Mapping from page identifier to linked article titles.

        Raises:
            ValueError: If concurrency is not positive.
        """
        if concurrency <= 0:
            raise ValueError("Concurrency must be greater than zero.")

        semaphore = asyncio.Semaphore(concurrency)

        async def fetch(
            page_id: int,
        ) -> tuple[int, tuple[str, ...]]:
            async with semaphore:
                titles = await self.get_article_link_titles(page_id)

                return page_id, titles

        results = await asyncio.gather(*(fetch(page_id) for page_id in page_ids))

        return dict(results)

    @classmethod
    def _build_article_url(cls, title: str) -> str:
        """Build a canonical Wikipedia article URL.

        Args:
            title: Wikipedia article title.

        Returns:
            Canonical article URL.
        """
        normalized_title = quote(
            title.replace(" ", "_"),
            safe="()_,-",
        )

        return f"{cls.ARTICLE_BASE_URL}{normalized_title}"

    @staticmethod
    def _normalize_category_name(category: str) -> str:
        """Remove the MediaWiki category namespace prefix.

        Args:
            category: Raw category name returned by MediaWiki.

        Returns:
            Category name without the ``Category:`` prefix.
        """
        prefix = "Category:"

        if category.startswith(prefix):
            return category[len(prefix) :]

        return category

    @staticmethod
    def _extract_summary(content: str) -> str | None:
        """Extract a compact article summary from plain text.

        Args:
            content: Complete article text.

        Returns:
            First non-empty paragraph or ``None``.
        """
        paragraphs = (paragraph.strip() for paragraph in content.split("\n\n"))

        return next(
            (paragraph for paragraph in paragraphs if paragraph),
            None,
        )
