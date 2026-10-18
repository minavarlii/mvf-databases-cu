"""Benchmark MariaDB semantic, hybrid, and linked search strategies."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select

from backend.app.db import database_manager
from backend.app.db.models import (
    Article,
    ArticleLink,
    Chunk,
)
from backend.app.db.queries import (
    QueryPlanRow,
    VectorQueries,
    VectorSearchResult,
)
from backend.app.services import EmbeddingService
from experiments.environment import EnvironmentMetadata, collect_environment

RESULTS_DIRECTORY = Path("experiments/results")


@dataclass(frozen=True, slots=True)
class DatasetStats:
    """Represent dataset size at benchmark time."""

    article_count: int
    vector_count: int
    article_link_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkStats:
    """Represent latency statistics for one search strategy."""

    runs: int
    mean_ms: float
    median_ms: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    stddev_ms: float


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Represent one search strategy benchmark."""

    latency: BenchmarkStats
    execution_plan: tuple[QueryPlanRow, ...]


@dataclass(frozen=True, slots=True)
class SearchStrategiesResult:
    """Represent the complete search-strategy experiment."""

    query: str
    limit: int
    warmups: int
    runs: int
    hybrid_category: str
    linked_source_title: str
    dataset: DatasetStats
    environment: EnvironmentMetadata
    semantic: StrategyResult
    hybrid: StrategyResult
    linked: StrategyResult


SearchOperation = Callable[
    [],
    Awaitable[list[VectorSearchResult]],
]


def percentile(
    values: list[float],
    fraction: float,
) -> float:
    """Return a percentile using linear interpolation.

    Args:
        values: Numeric samples.
        fraction: Percentile from 0.0 to 1.0.

    Returns:
        Interpolated percentile value.

    Raises:
        ValueError: If inputs are invalid.
    """
    if not values:
        raise ValueError("At least one value is required.")

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("Percentile fraction must be between 0 and 1.")

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * fraction

    lower_index = int(position)

    upper_index = min(
        lower_index + 1,
        len(ordered) - 1,
    )

    weight = position - lower_index

    return ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight


def calculate_stats(
    samples: list[float],
) -> BenchmarkStats:
    """Calculate latency statistics.

    Args:
        samples: Latency samples in milliseconds.

    Returns:
        Aggregate benchmark statistics.

    Raises:
        ValueError: If samples are empty.
    """
    if not samples:
        raise ValueError("At least one benchmark sample is required.")

    return BenchmarkStats(
        runs=len(samples),
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        p50_ms=percentile(
            samples,
            0.50,
        ),
        p95_ms=percentile(
            samples,
            0.95,
        ),
        min_ms=min(samples),
        max_ms=max(samples),
        stddev_ms=(statistics.stdev(samples) if len(samples) > 1 else 0.0),
    )


async def benchmark_operation(
    operation: SearchOperation,
    *,
    warmups: int,
    runs: int,
) -> BenchmarkStats:
    """Benchmark one asynchronous database operation.

    Args:
        operation: Search operation.
        warmups: Unmeasured warm-up executions.
        runs: Measured executions.

    Returns:
        Latency statistics.

    Raises:
        ValueError: If benchmark configuration is invalid.
    """
    if warmups < 0:
        raise ValueError("Warmups must not be negative.")

    if runs <= 0:
        raise ValueError("Runs must be greater than zero.")

    for _ in range(warmups):
        await operation()

    samples: list[float] = []

    for _ in range(runs):
        started = perf_counter()

        await operation()

        elapsed_ms = (perf_counter() - started) * 1000.0

        samples.append(elapsed_ms)

    return calculate_stats(samples)


async def load_dataset_stats() -> DatasetStats:
    """Load dataset counts from MariaDB.

    Returns:
        Current article, vector, and article-link counts.
    """
    async with database_manager.session() as session:
        article_count = await session.scalar(select(func.count(Article.id)))

        vector_count = await session.scalar(select(func.count(Chunk.id)))

        article_link_count = await session.scalar(
            select(func.count(ArticleLink.source_article_id))
        )

    return DatasetStats(
        article_count=int(article_count or 0),
        vector_count=int(vector_count or 0),
        article_link_count=int(article_link_count or 0),
    )


async def run_benchmark(
    *,
    query: str,
    hybrid_category: str,
    linked_source_title: str,
    limit: int,
    warmups: int,
    runs: int,
) -> SearchStrategiesResult:
    """Run the complete MariaDB search-strategy experiment.

    Embedding generation is intentionally performed before timing.
    Measured latency therefore represents database retrieval latency.

    Args:
        query: Natural-language query.
        hybrid_category: Relational category filter.
        linked_source_title: Source article for graph search.
        limit: Maximum returned chunks.
        warmups: Warm-up executions per strategy.
        runs: Measured executions per strategy.

    Returns:
        Complete benchmark and EXPLAIN results.

    Raises:
        ValueError: If benchmark parameters are invalid.
    """
    normalized_query = query.strip()
    normalized_category = hybrid_category.strip()
    normalized_source_title = linked_source_title.strip()

    if not normalized_query:
        raise ValueError("Query must not be empty.")

    if not normalized_category:
        raise ValueError("Hybrid category must not be empty.")

    if not normalized_source_title:
        raise ValueError("Linked source title must not be empty.")

    if limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    dataset = await load_dataset_stats()
    environment = await collect_environment()

    embedding_service = EmbeddingService()

    embedding = await embedding_service.embed_text(normalized_query)

    async with database_manager.session() as session:
        vector_queries = VectorQueries(session)

        semantic_latency = await benchmark_operation(
            lambda: (
                vector_queries.semantic_search(
                    embedding=embedding,
                    limit=limit,
                )
            ),
            warmups=warmups,
            runs=runs,
        )

        semantic_plan = await vector_queries.explain_semantic_search(
            embedding=embedding,
            limit=limit,
        )

        hybrid_latency = await benchmark_operation(
            lambda: (
                vector_queries.hybrid_search(
                    embedding=embedding,
                    category=normalized_category,
                    limit=limit,
                )
            ),
            warmups=warmups,
            runs=runs,
        )

        hybrid_plan = await vector_queries.explain_hybrid_search(
            embedding=embedding,
            category=normalized_category,
            limit=limit,
        )

        linked_latency = await benchmark_operation(
            lambda: (
                vector_queries.linked_search(
                    embedding=embedding,
                    source_title=(normalized_source_title),
                    limit=limit,
                )
            ),
            warmups=warmups,
            runs=runs,
        )

        linked_plan = await vector_queries.explain_linked_search(
            embedding=embedding,
            source_title=(normalized_source_title),
            limit=limit,
        )

    return SearchStrategiesResult(
        query=normalized_query,
        limit=limit,
        warmups=warmups,
        runs=runs,
        hybrid_category=(normalized_category),
        linked_source_title=(normalized_source_title),
        dataset=dataset,
        environment=environment,
        semantic=StrategyResult(
            latency=semantic_latency,
            execution_plan=tuple(semantic_plan),
        ),
        hybrid=StrategyResult(
            latency=hybrid_latency,
            execution_plan=tuple(hybrid_plan),
        ),
        linked=StrategyResult(
            latency=linked_latency,
            execution_plan=tuple(linked_plan),
        ),
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark semantic, hybrid, and linked MariaDB-native vector search."
        )
    )

    parser.add_argument(
        "--query",
        default="neural network training",
    )

    parser.add_argument(
        "--category",
        default="Machine learning",
    )

    parser.add_argument(
        "--source-title",
        default="Machine learning",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--warmups",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=50,
    )

    return parser.parse_args()


def print_stats(
    name: str,
    result: StrategyResult,
) -> None:
    """Print one strategy result."""
    stats = result.latency

    indexes = [row.key for row in result.execution_plan if row.key is not None]

    print(
        f"{name:<10} "
        f"mean={stats.mean_ms:.3f} ms  "
        f"median={stats.median_ms:.3f} ms  "
        f"p95={stats.p95_ms:.3f} ms"
    )

    print(f"{'':<10} indexes={', '.join(indexes) or 'none'}")


async def async_main() -> None:
    """Run benchmark and persist results."""
    args = parse_args()

    try:
        result = await run_benchmark(
            query=args.query,
            hybrid_category=args.category,
            linked_source_title=(args.source_title),
            limit=args.limit,
            warmups=args.warmups,
            runs=args.runs,
        )

        RESULTS_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = RESULTS_DIRECTORY / "search_strategies.json"

        output_path.write_text(
            json.dumps(
                asdict(result),
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print("MariaDB search strategy benchmark")
        print()

        print(f"Articles: {result.dataset.article_count}")
        print(f"Vectors: {result.dataset.vector_count}")
        print(f"Article links: {result.dataset.article_link_count}")

        print()
        print(f"Query: {result.query}")
        print(f"Hybrid category: {result.hybrid_category}")
        print(f"Linked source: {result.linked_source_title}")
        print(f"Limit: {result.limit}")
        print(f"Warmups: {result.warmups}")
        print(f"Runs: {result.runs}")
        print()

        print_stats(
            "Semantic",
            result.semantic,
        )
        print_stats(
            "Hybrid",
            result.hybrid,
        )
        print_stats(
            "Linked",
            result.linked,
        )

        print()
        print(f"Saved results to {output_path}")

    finally:
        await database_manager.dispose()


def main() -> None:
    """Run the asynchronous benchmark entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
