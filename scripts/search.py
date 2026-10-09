"""Run semantic search against MariaDB vector data."""

import argparse
import asyncio

from backend.app.db import database_manager
from backend.app.services import EmbeddingService, SearchService


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Search MVF using MariaDB native vectors.",
    )

    parser.add_argument(
        "query",
        help="Natural-language search query.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of results.",
    )

    return parser.parse_args()


async def run(
    *,
    query: str,
    limit: int,
) -> None:
    """Execute semantic search.

    Args:
        query: Natural-language search query.
        limit: Maximum number of results.
    """
    embedding_service = EmbeddingService()

    async with database_manager.session() as session:
        search_service = SearchService(
            session=session,
            embedding_service=embedding_service,
        )

        results = await search_service.search(
            query,
            limit=limit,
        )

    await database_manager.dispose()

    if not results:
        print("No results found.")
        return

    for position, result in enumerate(results, start=1):
        preview = result.content.replace("\n", " ")[:300]

        print()
        print(f"[{position}] {result.article_title}")
        print(f"Chunk: {result.chunk_index} | Distance: {result.distance:.6f}")
        print(preview)


async def main() -> None:
    """Run the semantic-search command."""
    arguments = parse_arguments()

    await run(
        query=arguments.query,
        limit=arguments.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
