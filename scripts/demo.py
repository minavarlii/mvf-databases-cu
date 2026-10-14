"""Run a guided MariaDB-native vector-search demonstration."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import text

from backend.app.db import database_manager
from backend.app.services import EmbeddingService, SearchExecution, SearchService

DEFAULT_QUERY = "neural network training"
DEFAULT_CATEGORY = "Machine learning"
DEFAULT_SOURCE_TITLE = "Machine learning"
DEFAULT_LIMIT = 3

DATABASE_SUMMARY_SQL = """
SELECT
    VERSION() AS version,
    (SELECT COUNT(*) FROM articles) AS articles,
    (SELECT COUNT(*) FROM chunks) AS vectors,
    (SELECT COUNT(*) FROM article_links) AS article_links
"""

VECTOR_INDEX_SQL = """
SELECT
    INDEX_NAME,
    INDEX_TYPE,
    INDEX_COMMENT
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'chunks'
  AND INDEX_NAME = 'ix_chunks_embedding'
LIMIT 1
"""


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Demonstrate semantic, hybrid, and graph-constrained "
            "MariaDB vector search with SQL, timings, and EXPLAIN."
        )
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Natural-language query used by all demo searches.",
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Wikipedia category used by hybrid search.",
    )
    parser.add_argument(
        "--source-title",
        default=DEFAULT_SOURCE_TITLE,
        help="Source Wikipedia article used by linked search.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of results per search.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete demo as JSON.",
    )
    return parser.parse_args()


def _format_plan(execution: SearchExecution) -> list[dict[str, Any]]:
    """Convert EXPLAIN rows to serializable dictionaries."""
    return [
        {
            "select_id": row.select_id,
            "select_type": row.select_type,
            "table": row.table,
            "access_type": row.access_type,
            "possible_keys": row.possible_keys,
            "key": row.key,
            "rows": row.rows,
            "extra": row.extra,
        }
        for row in execution.debug.execution_plan
    ]


def _format_results(execution: SearchExecution) -> list[dict[str, Any]]:
    """Convert search results to serializable dictionaries."""
    return [
        {
            "rank": index,
            "article_title": result.article_title,
            "chunk_index": result.chunk_index,
            "distance": result.distance,
            "preview": result.content.replace("\n", " ")[:220],
        }
        for index, result in enumerate(execution.results, start=1)
    ]


def _format_execution(
    *,
    mode: str,
    query: str,
    execution: SearchExecution,
    category: str | None = None,
    source_title: str | None = None,
) -> dict[str, Any]:
    """Build a serializable representation of one demo search."""
    return {
        "mode": mode,
        "query": query,
        "category": category,
        "source_title": source_title,
        "results": _format_results(execution),
        "sql": execution.debug.sql.strip(),
        "parameters": execution.debug.parameters,
        "timings_ms": {
            "embedding": execution.debug.embedding_ms,
            "search": execution.debug.search_ms,
            "explain": execution.debug.explain_ms,
            "total": execution.debug.total_ms,
        },
        "execution_plan": _format_plan(execution),
    }


def _print_rule(character: str = "-", width: int = 78) -> None:
    print(character * width)


def _print_execution(payload: dict[str, Any]) -> None:
    """Print one search mode as a readable worked example."""
    title = str(payload["mode"]).upper()
    print()
    _print_rule("=")
    print(title)
    _print_rule("=")

    print(f"Query: {payload['query']}")

    if payload["category"] is not None:
        print(f"Category: {payload['category']}")

    if payload["source_title"] is not None:
        print(f"Source article: {payload['source_title']}")

    print()
    print("Top results")
    _print_rule()

    results = payload["results"]
    if not results:
        print("No results found.")
    else:
        for result in results:
            print(
                f"{result['rank']}. {result['article_title']} "
                f"(chunk={result['chunk_index']}, "
                f"distance={result['distance']:.6f})"
            )
            print(f"   {result['preview']}")

    print()
    print("MariaDB SQL")
    _print_rule()
    print(payload["sql"])

    print()
    print("Parameters")
    _print_rule()
    for key, value in payload["parameters"].items():
        print(f"{key}: {value}")

    timings = payload["timings_ms"]
    print()
    print("Timings")
    _print_rule()
    print(f"Embedding: {timings['embedding']:.3f} ms")
    print(f"Search:    {timings['search']:.3f} ms")
    print(f"EXPLAIN:   {timings['explain']:.3f} ms")
    print(f"Total:     {timings['total']:.3f} ms")

    print()
    print("EXPLAIN")
    _print_rule()
    plan = payload["execution_plan"]
    if not plan:
        print("No execution-plan rows returned.")
    else:
        for row in plan:
            print(
                f"table={row['table']} | "
                f"type={row['access_type']} | "
                f"key={row['key']} | "
                f"possible_keys={row['possible_keys']} | "
                f"rows={row['rows']} | "
                f"extra={row['extra']}"
            )


async def run(
    *,
    query: str,
    category: str,
    source_title: str,
    limit: int,
    output_json: bool,
) -> None:
    """Run the complete guided demo."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero.")

    embedding_service = EmbeddingService()

    try:
        async with database_manager.session() as session:
            summary_result = await session.execute(text(DATABASE_SUMMARY_SQL))
            summary_row = summary_result.mappings().one()

            index_result = await session.execute(text(VECTOR_INDEX_SQL))
            index_row = index_result.mappings().first()

            search_service = SearchService(
                session=session,
                embedding_service=embedding_service,
            )

            semantic = await search_service.search_with_debug(
                query,
                limit=limit,
            )
            hybrid = await search_service.hybrid_search_with_debug(
                query,
                category=category,
                limit=limit,
            )
            linked = await search_service.linked_search_with_debug(
                query,
                source_title=source_title,
                limit=limit,
            )

        database_payload: dict[str, Any] = {
            "version": str(summary_row["version"]),
            "articles": int(summary_row["articles"]),
            "vectors": int(summary_row["vectors"]),
            "article_links": int(summary_row["article_links"]),
            "vector_index": (
                {
                    "name": str(index_row["INDEX_NAME"]),
                    "type": str(index_row["INDEX_TYPE"]),
                    "comment": str(index_row["INDEX_COMMENT"]),
                }
                if index_row is not None
                else None
            ),
        }

        searches_payload: list[dict[str, Any]] = [
            _format_execution(
                mode="semantic search",
                query=query,
                execution=semantic,
            ),
            _format_execution(
                mode="hybrid search",
                query=query,
                category=category,
                execution=hybrid,
            ),
            _format_execution(
                mode="linked search",
                query=query,
                source_title=source_title,
                execution=linked,
            ),
        ]

        payload: dict[str, Any] = {
            "database": database_payload,
            "searches": searches_payload,
        }

        if output_json:
            print(json.dumps(payload, indent=2))
            return

        print()
        _print_rule("=")
        print("MVF — MariaDB Native Vector Search Demo")
        _print_rule("=")
        print(f"MariaDB:       {database_payload['version']}")
        print(f"Articles:      {database_payload['articles']}")
        print(f"Vector chunks: {database_payload['vectors']}")
        print(f"Article links: {database_payload['article_links']}")

        vector_index = database_payload["vector_index"]
        if vector_index is not None:
            print(f"Vector index:  {vector_index['name']} ({vector_index['type']})")

        for search_payload in searches_payload:
            _print_execution(search_payload)

        print()
        _print_rule("=")
        print("Why this is MariaDB-native")
        _print_rule("=")
        print(
            "Vector storage, cosine ranking, relational filters, graph joins, "
            "index selection, and EXPLAIN all run inside MariaDB."
        )
        print("No separate vector database is used.")

    finally:
        await database_manager.dispose()


async def main() -> None:
    """Run command."""
    arguments = parse_arguments()
    await run(
        query=arguments.query,
        category=arguments.category,
        source_title=arguments.source_title,
        limit=arguments.limit,
        output_json=arguments.json,
    )


if __name__ == "__main__":
    asyncio.run(main())
