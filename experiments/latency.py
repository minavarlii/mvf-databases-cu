"""Benchmark MariaDB vector-search latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService

RESULTS_DIRECTORY = Path("experiments/results")

DEFAULT_RUNS = 50
DEFAULT_WARMUP_RUNS = 5


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Benchmark MariaDB vector-search latency.",
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

    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help="Number of measured query executions.",
    )

    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=DEFAULT_WARMUP_RUNS,
        help="Number of unmeasured warm-up executions.",
    )

    return parser.parse_args()


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    """Calculate a percentile using linear interpolation.

    Args:
        values: Numeric sample values.
        percentile_value: Percentile between 0 and 100.

    Returns:
        Interpolated percentile value.

    Raises:
        ValueError: If no values are supplied.
    """
    if not values:
        raise ValueError("Cannot calculate a percentile of no values.")

    ordered = sorted(values)

    position = percentile_value / 100.0 * (len(ordered) - 1)

    lower_index = int(position)
    upper_index = min(
        lower_index + 1,
        len(ordered) - 1,
    )

    fraction = position - lower_index

    return (
        ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction
    )


async def run(
    *,
    query: str,
    category: str | None,
    limit: int,
    runs: int,
    warmup_runs: int,
) -> None:
    """Run the vector-search latency benchmark.

    Embedding generation is intentionally excluded from measured latency.
    Only MariaDB query execution is measured.

    Args:
        query: Natural-language search query.
        category: Optional relational category filter.
        limit: Maximum number of results.
        runs: Number of measured executions.
        warmup_runs: Number of unmeasured warm-up executions.

    Raises:
        ValueError: If benchmark parameters are invalid.
    """
    if runs <= 0:
        raise ValueError("Runs must be greater than zero.")

    if warmup_runs < 0:
        raise ValueError("Warm-up runs cannot be negative.")

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    embedding_service = EmbeddingService()

    print("Generating query embedding...")

    embedding = await embedding_service.embed_text(query)

    search_type = "hybrid" if category is not None else "semantic"

    latencies_ms: list[float] = []

    async with database_manager.session() as session:
        vector_queries = VectorQueries(session)

        async def execute_search() -> None:
            """Execute one benchmark search."""
            if category is None:
                await vector_queries.semantic_search(
                    embedding=embedding,
                    limit=limit,
                )
                return

            await vector_queries.hybrid_search(
                embedding=embedding,
                category=category,
                limit=limit,
            )

        print(f"Running {warmup_runs} warm-up queries...")

        for _ in range(warmup_runs):
            await execute_search()

        print(f"Running {runs} measured queries...")

        for _ in range(runs):
            started_at = perf_counter()

            await execute_search()

            elapsed_ms = (perf_counter() - started_at) * 1000.0

            latencies_ms.append(elapsed_ms)

    await database_manager.dispose()

    mean_ms = statistics.mean(latencies_ms)
    median_ms = statistics.median(latencies_ms)

    stddev_ms = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0

    result = {
        "executed_at": datetime.now(UTC).isoformat(),
        "search_type": search_type,
        "query": query,
        "category": category,
        "limit": limit,
        "runs": runs,
        "warmup_runs": warmup_runs,
        "latency_ms": {
            "mean": mean_ms,
            "median": median_ms,
            "p50": percentile(latencies_ms, 50),
            "p95": percentile(latencies_ms, 95),
            "min": min(latencies_ms),
            "max": max(latencies_ms),
            "stddev": stddev_ms,
        },
        "samples_ms": latencies_ms,
    }

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = RESULTS_DIRECTORY / f"latency_{search_type}_{timestamp}.json"

    output_path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Search type: {search_type}")
    print(f"Runs: {runs}")
    print(f"Mean:   {mean_ms:.3f} ms")
    print(f"Median: {median_ms:.3f} ms")
    print(f"P50:    {percentile(latencies_ms, 50):.3f} ms")
    print(f"P95:    {percentile(latencies_ms, 95):.3f} ms")
    print(f"Min:    {min(latencies_ms):.3f} ms")
    print(f"Max:    {max(latencies_ms):.3f} ms")
    print(f"Stddev: {stddev_ms:.3f} ms")
    print()
    print(f"Saved result to {output_path}")


async def main() -> None:
    """Run the latency experiment."""
    arguments = parse_arguments()

    await run(
        query=arguments.query,
        category=arguments.category,
        limit=arguments.limit,
        runs=arguments.runs,
        warmup_runs=arguments.warmup_runs,
    )


if __name__ == "__main__":
    asyncio.run(main())
