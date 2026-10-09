"""Run and persist MariaDB vector-search EXPLAIN experiments."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService

RESULTS_DIRECTORY = Path("experiments/results")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run MariaDB vector-search EXPLAIN experiments.",
    )

    parser.add_argument(
        "query",
        help="Natural-language query.",
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
    """Run and persist an EXPLAIN experiment.

    Args:
        query: Natural-language search query.
        category: Optional relational category filter.
        limit: Maximum number of search results.
    """
    embedding_service = EmbeddingService()
    embedding = await embedding_service.embed_text(query)

    async with database_manager.session() as session:
        vector_queries = VectorQueries(session)

        if category is None:
            search_type = "semantic"

            plan = await vector_queries.explain_semantic_search(
                embedding=embedding,
                limit=limit,
            )
        else:
            search_type = "hybrid"

            plan = await vector_queries.explain_hybrid_search(
                embedding=embedding,
                category=category,
                limit=limit,
            )

    await database_manager.dispose()

    payload = {
        "executed_at": datetime.now(UTC).isoformat(),
        "search_type": search_type,
        "query": query,
        "category": category,
        "limit": limit,
        "plan": [asdict(row) for row in plan],
    }

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"explain_{search_type}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )

    output_path = RESULTS_DIRECTORY / filename

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Saved EXPLAIN result to {output_path}")

    for row in plan:
        print(
            f"table={row.table} | "
            f"type={row.access_type} | "
            f"key={row.key} | "
            f"rows={row.rows} | "
            f"extra={row.extra}"
        )


async def main() -> None:
    """Run the EXPLAIN experiment."""
    arguments = parse_arguments()

    await run(
        query=arguments.query,
        category=arguments.category,
        limit=arguments.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
