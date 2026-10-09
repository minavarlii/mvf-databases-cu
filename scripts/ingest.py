"""Ingest Wikipedia articles into the MVF database."""

import argparse
import asyncio
from pathlib import Path

from backend.app.clients import MediaWikiClient
from backend.app.db import database_manager
from backend.app.services import IngestionService


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Ingest Wikipedia articles into MVF.",
    )

    parser.add_argument(
        "--category",
        required=True,
        help="Wikipedia category name.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of articles to ingest.",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum number of concurrent MediaWiki requests.",
    )

    return parser.parse_args()


async def run(
    *,
    category: str,
    limit: int,
    concurrency: int,
) -> None:
    """Run the Wikipedia ingestion pipeline.

    Args:
        category: Wikipedia category name.
        limit: Maximum number of articles to ingest.
    """
    if concurrency <= 0:
        raise ValueError("Concurrency must be greater than zero.")

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    raw_data_directory = Path("data/raw")

    async with MediaWikiClient() as mediawiki_client:
        async with database_manager.session() as session:
            service = IngestionService(
                session=session,
                mediawiki_client=mediawiki_client,
                raw_data_directory=raw_data_directory,
            )

            result = await service.ingest_category(
                category,
                limit=limit,
                concurrency=concurrency,
            )

            await session.commit()

    await database_manager.dispose()

    print(
        f"Successfully ingested "
        f"{len(result.articles)} articles "
        f"from category '{category}'."
    )

    print(f"Persisted {result.article_links} directed links within the local corpus.")


async def main() -> None:
    """Run the ingestion command."""
    arguments = parse_arguments()

    await run(
        category=arguments.category,
        limit=arguments.limit,
        concurrency=arguments.concurrency,
    )


if __name__ == "__main__":
    asyncio.run(main())
