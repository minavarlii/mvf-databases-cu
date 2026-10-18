"""Compare filtered hybrid search with the vector index enabled and ignored."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.app.db import database_manager
from backend.app.db.queries import QueryPlanRow, VectorQueries
from backend.app.services import EmbeddingService
from experiments.environment import EnvironmentMetadata, collect_environment
from experiments.index_vs_bruteforce import set_vector_index_ignored

RESULTS_DIRECTORY = Path("experiments/results")
DEFAULT_QUERY = "neural network training"
DEFAULT_CATEGORY = "Machine learning"
DEFAULT_LIMIT = 5
DEFAULT_WARMUPS = 5
DEFAULT_RUNS = 50


@dataclass(frozen=True, slots=True)
class LatencyStats:
    """Repeated database latency statistics."""

    runs: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    stddev_ms: float
    minimum_ms: float
    maximum_ms: float


@dataclass(frozen=True, slots=True)
class ModeResult:
    """One filtered-search execution mode."""

    latency: LatencyStats
    execution_plan: tuple[QueryPlanRow, ...]
    result_signature: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True, slots=True)
class HybridIndexStudy:
    """Complete indexed-versus-ignored filtered ANN comparison."""

    executed_at: str
    environment: EnvironmentMetadata
    query: str
    category: str
    limit: int
    warmups: int
    runs: int
    indexed: ModeResult
    index_ignored: ModeResult
    same_top_k: bool
    mean_speedup: float


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile."""
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def summarize(samples: list[float]) -> LatencyStats:
    """Summarize repeated latency samples."""
    return LatencyStats(
        runs=len(samples),
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        p95_ms=percentile(samples, 0.95),
        stddev_ms=statistics.stdev(samples) if len(samples) > 1 else 0.0,
        minimum_ms=min(samples),
        maximum_ms=max(samples),
    )


async def measure_mode(
    *,
    embedding: list[float],
    category: str,
    limit: int,
    warmups: int,
    runs: int,
) -> ModeResult:
    """Measure one filtered-search optimizer mode."""
    samples: list[float] = []

    async with database_manager.session() as session:
        queries = VectorQueries(session)

        for _ in range(warmups):
            await queries.hybrid_search(
                embedding=embedding,
                category=category,
                limit=limit,
            )

        results = []
        for _ in range(runs):
            started = time.perf_counter()
            results = await queries.hybrid_search(
                embedding=embedding,
                category=category,
                limit=limit,
            )
            samples.append((time.perf_counter() - started) * 1000)

        plan = await queries.explain_hybrid_search(
            embedding=embedding,
            category=category,
            limit=limit,
        )

    signature = tuple(
        (result.chunk_id, result.article_id, result.chunk_index) for result in results
    )

    return ModeResult(
        latency=summarize(samples),
        execution_plan=tuple(plan),
        result_signature=signature,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare category-filtered vector search with the vector index "
            "enabled and optimizer-ignored."
        )
    )
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--category", default=DEFAULT_CATEGORY)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    return parser.parse_args()


async def async_main() -> None:
    """Run the filtered ANN/index interaction study."""
    args = parse_args()
    if args.limit <= 0 or args.runs <= 0 or args.warmups < 0:
        raise ValueError("limit/runs must be positive and warmups non-negative.")

    embedding = await EmbeddingService().embed_text(args.query)
    environment = await collect_environment()

    await set_vector_index_ignored(ignored=False)
    indexed = await measure_mode(
        embedding=embedding,
        category=args.category,
        limit=args.limit,
        warmups=args.warmups,
        runs=args.runs,
    )

    try:
        await set_vector_index_ignored(ignored=True)
        index_ignored = await measure_mode(
            embedding=embedding,
            category=args.category,
            limit=args.limit,
            warmups=args.warmups,
            runs=args.runs,
        )
    finally:
        await set_vector_index_ignored(ignored=False)

    speedup = index_ignored.latency.mean_ms / indexed.latency.mean_ms
    study = HybridIndexStudy(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        query=args.query,
        category=args.category,
        limit=args.limit,
        warmups=args.warmups,
        runs=args.runs,
        indexed=indexed,
        index_ignored=index_ignored,
        same_top_k=(indexed.result_signature == index_ignored.result_signature),
        mean_speedup=speedup,
    )

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"hybrid_index_probe_{timestamp}.json"
    output_path.write_text(
        json.dumps(asdict(study), indent=2),
        encoding="utf-8",
    )

    print(f"Indexed mean:      {indexed.latency.mean_ms:.3f} ms")
    print(f"Index-ignored mean:{index_ignored.latency.mean_ms:.3f} ms")
    print(f"Mean speedup:      {speedup:.2f}x")
    print(f"Same top-k:        {study.same_top_k}")
    print(f"Saved results to {output_path}")

    await database_manager.dispose()


def main() -> None:
    """Run the async experiment entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
