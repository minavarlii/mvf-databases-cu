"""Compare current and derived-table linked vector search."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import database_manager
from backend.app.services import EmbeddingService

QUERY = "neural network training"
SOURCE_TITLE = "Machine learning"

LIMIT = 5
WARMUP_RUNS = 5
MEASURED_RUNS = 30


CURRENT_LINKED_SQL = """
SELECT
    c.id AS chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = :source_title
ORDER BY distance ASC
LIMIT :limit
"""


CURRENT_LINKED_EXPLAIN_SQL = """
EXPLAIN
SELECT
    c.id AS chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = :source_title
ORDER BY distance ASC
LIMIT :limit
"""


PROPOSED_LINKED_SQL = """
SELECT
    c.chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    c.distance
FROM (
    SELECT
        id AS chunk_id,
        article_id,
        chunk_index,
        content,
        token_count,
        VEC_DISTANCE_COSINE(
            embedding,
            VEC_FromText(:embedding)
        ) AS distance
    FROM chunks
    WHERE article_id IN (
        SELECT al.target_article_id
        FROM article_links AS al
        INNER JOIN articles AS source
            ON source.id = al.source_article_id
        WHERE source.title = :source_title
    )
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS target
    ON target.id = c.article_id
ORDER BY c.distance ASC
"""


PROPOSED_LINKED_EXPLAIN_SQL = """
EXPLAIN
SELECT
    c.chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    c.distance
FROM (
    SELECT
        id AS chunk_id,
        article_id,
        chunk_index,
        content,
        token_count,
        VEC_DISTANCE_COSINE(
            embedding,
            VEC_FromText(:embedding)
        ) AS distance
    FROM chunks
    WHERE article_id IN (
        SELECT al.target_article_id
        FROM article_links AS al
        INNER JOIN articles AS source
            ON source.id = al.source_article_id
        WHERE source.title = :source_title
    )
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS target
    ON target.id = c.article_id
ORDER BY c.distance ASC
"""


@dataclass(frozen=True)
class BenchmarkResult:
    """Store latency measurements."""

    mean_ms: float
    median_ms: float
    p95_ms: float
    minimum_ms: float
    maximum_ms: float


def serialize_embedding(
    embedding: Sequence[float],
) -> str:
    """Serialize an embedding for VEC_FromText."""
    return json.dumps(
        list(embedding),
        separators=(",", ":"),
    )


def percentile(
    values: list[float],
    fraction: float,
) -> float:
    """Return nearest-rank percentile."""
    ordered = sorted(values)

    index = round((len(ordered) - 1) * fraction)

    return ordered[index]


async def execute_query(
    session: AsyncSession,
    sql: str,
    parameters: dict[str, str | int],
) -> list[RowMapping]:
    """Execute one query."""
    result = await session.execute(
        text(sql),
        parameters,
    )

    return list(result.mappings())


async def explain_query(
    session: AsyncSession,
    explain_sql: str,
    parameters: dict[str, str | int],
) -> list[RowMapping]:
    """Return EXPLAIN rows from a predeclared static SQL statement."""
    result = await session.execute(
        text(explain_sql),
        parameters,
    )

    return list(result.mappings())


async def benchmark_query(
    session: AsyncSession,
    sql: str,
    parameters: dict[str, str | int],
) -> BenchmarkResult:
    """Benchmark database execution."""
    for _ in range(WARMUP_RUNS):
        await execute_query(
            session,
            sql,
            parameters,
        )

    samples: list[float] = []

    for _ in range(MEASURED_RUNS):
        started = time.perf_counter()

        await execute_query(
            session,
            sql,
            parameters,
        )

        samples.append((time.perf_counter() - started) * 1000)

    return BenchmarkResult(
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        p95_ms=percentile(
            samples,
            0.95,
        ),
        minimum_ms=min(samples),
        maximum_ms=max(samples),
    )


def signature(
    rows: list[RowMapping],
) -> list[tuple[int, int, int]]:
    """Return stable result identifiers."""
    return [
        (
            int(row["chunk_id"]),
            int(row["article_id"]),
            int(row["chunk_index"]),
        )
        for row in rows
    ]


def print_plan(
    rows: list[RowMapping],
) -> None:
    """Print compact EXPLAIN rows."""
    for row in rows:
        print(
            "  "
            f"table={row.get('table')} "
            f"type={row.get('type')} "
            f"key={row.get('key')} "
            f"rows={row.get('rows')} "
            f"extra={row.get('Extra')}"
        )


def print_benchmark(
    result: BenchmarkResult,
) -> None:
    """Print benchmark result."""
    print(f"  mean:   {result.mean_ms:.3f} ms")
    print(f"  median: {result.median_ms:.3f} ms")
    print(f"  p95:    {result.p95_ms:.3f} ms")
    print(f"  min:    {result.minimum_ms:.3f} ms")
    print(f"  max:    {result.maximum_ms:.3f} ms")


async def run() -> None:
    """Run linked-search comparison."""
    embedding_service = EmbeddingService()

    embedding = await embedding_service.embed_text(QUERY)

    parameters: dict[str, str | int] = {
        "embedding": serialize_embedding(embedding),
        "source_title": SOURCE_TITLE,
        "limit": LIMIT,
    }

    try:
        async with database_manager.session() as session:
            current_rows = await execute_query(
                session,
                CURRENT_LINKED_SQL,
                parameters,
            )

            proposed_rows = await execute_query(
                session,
                PROPOSED_LINKED_SQL,
                parameters,
            )

            print()
            print("=" * 90)
            print("LINKED SEARCH")
            print("=" * 90)

            print(
                "Same top-k:",
                signature(current_rows) == signature(proposed_rows),
            )

            print()
            print("CURRENT PLAN")

            current_plan = await explain_query(
                session,
                CURRENT_LINKED_EXPLAIN_SQL,
                parameters,
            )

            print_plan(current_plan)

            print()
            print("PROPOSED PLAN")

            proposed_plan = await explain_query(
                session,
                PROPOSED_LINKED_EXPLAIN_SQL,
                parameters,
            )

            print_plan(proposed_plan)

            print()
            print("CURRENT LATENCY")

            current_benchmark = await benchmark_query(
                session,
                CURRENT_LINKED_SQL,
                parameters,
            )

            print_benchmark(current_benchmark)

            print()
            print("PROPOSED LATENCY")

            proposed_benchmark = await benchmark_query(
                session,
                PROPOSED_LINKED_SQL,
                parameters,
            )

            print_benchmark(proposed_benchmark)

    finally:
        await database_manager.dispose()


if __name__ == "__main__":
    asyncio.run(run())
