"""Benchmark semantic, hybrid, and linked retrieval over many queries."""

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
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService
from experiments.environment import EnvironmentMetadata, collect_environment
from experiments.ground_truth_latency import percentile
from experiments.recall import (
    GROUND_TRUTH_PATH,
    GroundTruthQuestion,
    load_ground_truth,
)

RESULTS_DIRECTORY = Path("experiments/results")
DEFAULT_CATEGORY = "Machine learning"
DEFAULT_SOURCE_TITLE = "Machine learning"
DEFAULT_LIMIT = 5
DEFAULT_PASSES = 5
DEFAULT_WARMUP_PASSES = 1


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """Ground-truth question paired with one precomputed embedding."""

    question: GroundTruthQuestion
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class PassStats:
    """Latency summary for one complete pass over all prepared questions."""

    pass_number: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    stddev_ms: float
    nonempty_results: int


@dataclass(frozen=True, slots=True)
class ModeStats:
    """Repeated latency summary for one retrieval mode."""

    mode: str
    measured_queries: int
    aggregate_mean_ms: float
    aggregate_median_ms: float
    aggregate_p95_ms: float
    between_pass_mean_stddev_ms: float
    nonempty_result_rate: float
    passes: tuple[PassStats, ...]


@dataclass(frozen=True, slots=True)
class MultiModeResult:
    """Complete multi-mode benchmark artifact."""

    executed_at: str
    environment: EnvironmentMetadata
    questions: int
    warmup_passes: int
    measured_passes: int
    limit: int
    category: str
    source_title: str
    semantic: ModeStats
    hybrid: ModeStats
    linked: ModeStats


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark all MariaDB retrieval modes across many queries."
    )
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    parser.add_argument(
        "--warmup-passes",
        type=int,
        default=DEFAULT_WARMUP_PASSES,
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--category", default=DEFAULT_CATEGORY)
    parser.add_argument("--source-title", default=DEFAULT_SOURCE_TITLE)
    return parser.parse_args()


async def prepare_questions() -> list[PreparedQuestion]:
    """Precompute embeddings so model latency is excluded from DB timings."""
    ground_truth = load_ground_truth(GROUND_TRUTH_PATH)
    embedding_service = EmbeddingService()
    embeddings = await embedding_service.embed_many(
        [item.question for item in ground_truth]
    )
    return [
        PreparedQuestion(question=item, embedding=embedding)
        for item, embedding in zip(ground_truth, embeddings, strict=True)
    ]


def summarize_pass(
    *,
    pass_number: int,
    latencies: list[float],
    nonempty_results: int,
) -> PassStats:
    """Summarize one measured pass."""
    return PassStats(
        pass_number=pass_number,
        mean_ms=statistics.mean(latencies),
        median_ms=statistics.median(latencies),
        p95_ms=percentile(latencies, 0.95),
        stddev_ms=(statistics.stdev(latencies) if len(latencies) > 1 else 0.0),
        nonempty_results=nonempty_results,
    )


def aggregate_mode(mode: str, passes: list[PassStats]) -> ModeStats:
    """Aggregate repeated pass summaries for one mode."""
    means = [item.mean_ms for item in passes]
    medians = [item.median_ms for item in passes]
    p95_values = [item.p95_ms for item in passes]
    total_queries = sum(1 for _ in passes) * passes[0].nonempty_results

    # The denominator must represent all queries, not only nonempty ones.
    # Each pass runs the same number of questions; infer it from the ratio later.
    # `measured_queries` is overwritten by the caller with the exact value.
    return ModeStats(
        mode=mode,
        measured_queries=total_queries,
        aggregate_mean_ms=statistics.mean(means),
        aggregate_median_ms=statistics.mean(medians),
        aggregate_p95_ms=statistics.mean(p95_values),
        between_pass_mean_stddev_ms=(
            statistics.stdev(means) if len(means) > 1 else 0.0
        ),
        nonempty_result_rate=0.0,
        passes=tuple(passes),
    )


async def run_mode(
    *,
    mode: str,
    prepared: list[PreparedQuestion],
    warmup_passes: int,
    measured_passes: int,
    limit: int,
    category: str,
    source_title: str,
) -> ModeStats:
    """Run one retrieval mode across all prepared questions repeatedly."""
    if warmup_passes < 0:
        raise ValueError("Warm-up passes must not be negative.")
    if measured_passes <= 0:
        raise ValueError("Measured passes must be greater than zero.")

    async with database_manager.session() as session:
        queries = VectorQueries(session)

        async def execute(item: PreparedQuestion) -> int:
            if mode == "semantic":
                results = await queries.semantic_search(
                    embedding=item.embedding,
                    limit=limit,
                )
            elif mode == "hybrid":
                results = await queries.hybrid_search(
                    embedding=item.embedding,
                    category=category,
                    limit=limit,
                )
            elif mode == "linked":
                results = await queries.linked_search(
                    embedding=item.embedding,
                    source_title=source_title,
                    limit=limit,
                )
            else:
                raise ValueError(f"Unsupported mode: {mode}")
            return len(results)

        for _ in range(warmup_passes):
            for item in prepared:
                await execute(item)

        pass_summaries: list[PassStats] = []
        total_nonempty = 0

        for pass_number in range(1, measured_passes + 1):
            latencies: list[float] = []
            nonempty = 0

            for item in prepared:
                started = time.perf_counter()
                result_count = await execute(item)
                latencies.append((time.perf_counter() - started) * 1000.0)
                if result_count > 0:
                    nonempty += 1

            total_nonempty += nonempty
            pass_summaries.append(
                summarize_pass(
                    pass_number=pass_number,
                    latencies=latencies,
                    nonempty_results=nonempty,
                )
            )

    means = [item.mean_ms for item in pass_summaries]
    medians = [item.median_ms for item in pass_summaries]
    p95_values = [item.p95_ms for item in pass_summaries]
    measured_queries = len(prepared) * measured_passes

    return ModeStats(
        mode=mode,
        measured_queries=measured_queries,
        aggregate_mean_ms=statistics.mean(means),
        aggregate_median_ms=statistics.mean(medians),
        aggregate_p95_ms=statistics.mean(p95_values),
        between_pass_mean_stddev_ms=(
            statistics.stdev(means) if len(means) > 1 else 0.0
        ),
        nonempty_result_rate=(total_nonempty / measured_queries),
        passes=tuple(pass_summaries),
    )


async def async_main() -> None:
    """Run and persist the complete multi-mode benchmark."""
    args = parse_args()
    prepared = await prepare_questions()
    environment = await collect_environment()

    results: dict[str, ModeStats] = {}
    for mode in ("semantic", "hybrid", "linked"):
        print(f"Benchmarking {mode} across {len(prepared)} questions...")
        results[mode] = await run_mode(
            mode=mode,
            prepared=prepared,
            warmup_passes=args.warmup_passes,
            measured_passes=args.passes,
            limit=args.limit,
            category=args.category,
            source_title=args.source_title,
        )
        item = results[mode]
        print(
            f"  mean={item.aggregate_mean_ms:.3f} ms  "
            f"p95={item.aggregate_p95_ms:.3f} ms  "
            f"between-pass stddev={item.between_pass_mean_stddev_ms:.3f} ms"
        )

    payload = MultiModeResult(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        questions=len(prepared),
        warmup_passes=args.warmup_passes,
        measured_passes=args.passes,
        limit=args.limit,
        category=args.category,
        source_title=args.source_title,
        semantic=results["semantic"],
        hybrid=results["hybrid"],
        linked=results["linked"],
    )

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIRECTORY / f"multi_mode_latency_{timestamp}.json"
    path.write_text(json.dumps(asdict(payload), indent=2) + "\n", encoding="utf-8")
    print(f"Saved results to {path}")

    await database_manager.dispose()


def main() -> None:
    """Run the asynchronous benchmark."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
