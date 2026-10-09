"""Inspect MariaDB query plans for vector search."""

import argparse
import asyncio

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Inspect MariaDB vector-search execution plans.",
    )

    parser.add_argument(
        "query",
        help="Natural-language search query.",
    )

    parser.add_argument(
        "--category",
        default=None,
        help="Optional category filter for hybrid search.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of search results.",
    )

    return parser.parse_args()


async def run(
    *,
    query: str,
    category: str | None,
    limit: int,
) -> None:
    """Run EXPLAIN for semantic or hybrid vector search."""
    embedding_service = EmbeddingService()
    embedding = await embedding_service.embed_text(query)

    async with database_manager.session() as session:
        vector_queries = VectorQueries(session)

        if category is None:
            plan = await vector_queries.explain_semantic_search(
                embedding=embedding,
                limit=limit,
            )
        else:
            plan = await vector_queries.explain_hybrid_search(
                embedding=embedding,
                category=category,
                limit=limit,
            )

    await database_manager.dispose()

    for row in plan:
        print(
            f"table={row.table} | "
            f"type={row.access_type} | "
            f"possible_keys={row.possible_keys} | "
            f"key={row.key} | "
            f"rows={row.rows} | "
            f"extra={row.extra}"
        )


async def main() -> None:
    """Run the EXPLAIN command."""
    arguments = parse_arguments()

    await run(
        query=arguments.query,
        category=arguments.category,
        limit=arguments.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
