"""Compare MariaDB vector-index search against brute-force search."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import text

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService

RESULTS_DIRECTORY = Path("experiments/results")

VECTOR_INDEX_IGNORED_SQL = """
ALTER TABLE chunks
ALTER INDEX ix_chunks_embedding IGNORED
""".strip()

VECTOR_INDEX_NOT_IGNORED_SQL = """
ALTER TABLE chunks
ALTER INDEX ix_chunks_embedding NOT IGNORED
""".strip()

DEFAULT_RUNS = 50
DEFAULT_WARMUP_RUNS = 5


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Compare MariaDB vector-index search against brute-force vector search."
        ),
    )

    parser.add_argument(
        "query",
        help="Natural-language search query.",
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
        help="Number of measured runs per search mode.",
    )

    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=DEFAULT_WARMUP_RUNS,
        help="Number of unmeasured warm-up runs.",
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
        ValueError: If values is empty.
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


def summarize(
    latencies_ms: list[float],
) -> dict[str, float]:
    """Summarize latency measurements.

    Args:
        latencies_ms: Query latency samples in milliseconds.

    Returns:
        Summary statistics.
    """
    return {
        "mean": statistics.mean(latencies_ms),
        "median": statistics.median(latencies_ms),
        "p50": percentile(latencies_ms, 50),
        "p95": percentile(latencies_ms, 95),
        "min": min(latencies_ms),
        "max": max(latencies_ms),
        "stddev": (statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0),
    }


async def set_vector_index_ignored(
    *,
    ignored: bool,
) -> None:
    """Enable or disable optimizer use of the vector index.

    Args:
        ignored: Whether the vector index should be ignored.
    """
    sql = VECTOR_INDEX_IGNORED_SQL if ignored else VECTOR_INDEX_NOT_IGNORED_SQL

    async with database_manager.session() as session:
        await session.execute(text(sql))
        await session.commit()


async def benchmark(
    *,
    embedding: list[float],
    limit: int,
    runs: int,
    warmup_runs: int,
) -> list[float]:
    """Benchmark semantic-search database latency.

    Args:
        embedding: Precomputed query embedding.
        limit: Maximum number of results.
        runs: Number of measured executions.
        warmup_runs: Number of unmeasured warm-up executions.

    Returns:
        Query latency samples in milliseconds.
    """
    latencies_ms: list[float] = []

    async with database_manager.session() as session:
        vector_queries = VectorQueries(session)

        for _ in range(warmup_runs):
            await vector_queries.semantic_search(
                embedding=embedding,
                limit=limit,
            )

        for _ in range(runs):
            started_at = perf_counter()

            await vector_queries.semantic_search(
                embedding=embedding,
                limit=limit,
            )

            elapsed_ms = (perf_counter() - started_at) * 1000.0

            latencies_ms.append(elapsed_ms)

    return latencies_ms


async def run(
    *,
    query: str,
    limit: int,
    runs: int,
    warmup_runs: int,
) -> None:
    """Run indexed and brute-force vector-search benchmarks.

    Args:
        query: Natural-language search query.
        limit: Maximum number of results.
        runs: Number of measured executions per mode.
        warmup_runs: Number of unmeasured executions per mode.

    Raises:
        ValueError: If benchmark parameters are invalid.
    """
    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    if runs <= 0:
        raise ValueError("Runs must be greater than zero.")

    if warmup_runs < 0:
        raise ValueError("Warm-up runs cannot be negative.")

    embedding_service = EmbeddingService()

    print("Generating query embedding...")
    embedding = await embedding_service.embed_text(query)

    print("Benchmarking VECTOR INDEX search...")

    await set_vector_index_ignored(
        ignored=False,
    )

    indexed_latencies = await benchmark(
        embedding=embedding,
        limit=limit,
        runs=runs,
        warmup_runs=warmup_runs,
    )

    print("Benchmarking brute-force search...")

    try:
        await set_vector_index_ignored(
            ignored=True,
        )

        brute_force_latencies = await benchmark(
            embedding=embedding,
            limit=limit,
            runs=runs,
            warmup_runs=warmup_runs,
        )
    finally:
        await set_vector_index_ignored(
            ignored=False,
        )

    await database_manager.dispose()

    indexed_summary = summarize(indexed_latencies)

    brute_force_summary = summarize(brute_force_latencies)

    speedup = brute_force_summary["mean"] / indexed_summary["mean"]

    async with database_manager.session() as session:
        vector_count = await session.scalar(text("SELECT COUNT(*) FROM chunks"))

    payload = {
        "executed_at": datetime.now(UTC).isoformat(),
        "query": query,
        "limit": limit,
        "runs": runs,
        "warmup_runs": warmup_runs,
        "vector_count": int(vector_count or 0),
        "indexed": {
            "summary_ms": indexed_summary,
            "samples_ms": indexed_latencies,
        },
        "brute_force": {
            "summary_ms": brute_force_summary,
            "samples_ms": brute_force_latencies,
        },
        "speedup": speedup,
    }

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = RESULTS_DIRECTORY / f"index_vs_bruteforce_{timestamp}.json"

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("VECTOR INDEX")
    print(f"Mean: {indexed_summary['mean']:.3f} ms")
    print(f"P95:  {indexed_summary['p95']:.3f} ms")

    print()
    print("BRUTE FORCE")
    print(f"Mean: {brute_force_summary['mean']:.3f} ms")
    print(f"P95:  {brute_force_summary['p95']:.3f} ms")

    print()
    print(f"Speedup: {speedup:.2f}x")
    print(f"Saved result to {output_path}")


async def main() -> None:
    """Run the vector-index comparison experiment."""
    arguments = parse_arguments()

    await run(
        query=arguments.query,
        limit=arguments.limit,
        runs=arguments.runs,
        warmup_runs=arguments.warmup_runs,
    )


if __name__ == "__main__":
    asyncio.run(main())
