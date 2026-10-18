"""Benchmark semantic search across the complete ground-truth query set."""

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
from experiments.recall import (
    DEFAULT_CANDIDATE_MULTIPLIER,
    DEFAULT_K_VALUES,
    GROUND_TRUTH_PATH,
    MINIMUM_CANDIDATE_LIMIT,
    GroundTruthQuestion,
    QuestionEvaluation,
    calculate_mrr,
    calculate_recall_at_k,
    find_relevant_result,
    load_corpus_statistics,
    load_ground_truth,
    unique_article_titles,
    validate_ground_truth_titles,
)

RESULTS_DIRECTORY = Path("experiments/results")
DEFAULT_PASSES = 5
DEFAULT_WARMUP_PASSES = 1


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """Ground-truth question paired with one precomputed embedding."""

    ground_truth: GroundTruthQuestion
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class QueryTiming:
    """Latency and retrieval result for one question in one measured pass."""

    question_id: str
    latency_ms: float
    first_relevant_rank: int | None


@dataclass(frozen=True, slots=True)
class PassResult:
    """One complete measured pass over all ground-truth questions."""

    pass_number: int
    mean_query_ms: float
    median_query_ms: float
    p95_query_ms: float
    stddev_query_ms: float
    recall_at_10: float
    mrr: float
    timings: tuple[QueryTiming, ...]


@dataclass(frozen=True, slots=True)
class GroundTruthLatencyStudy:
    """Complete repeated multi-query latency study."""

    executed_at: str
    environment: EnvironmentMetadata
    questions: int
    corpus_articles: int
    corpus_vectors: int
    candidate_limit: int
    warmup_passes: int
    measured_passes: int
    total_measured_queries: int
    aggregate_mean_query_ms: float
    aggregate_median_query_ms: float
    aggregate_p95_query_ms: float
    between_pass_mean_stddev_ms: float
    mean_recall_at_10: float
    mean_mrr: float
    passes: tuple[PassResult, ...]


def percentile(values: list[float], fraction: float) -> float:
    """Return an interpolated percentile from non-empty values."""
    if not values:
        raise ValueError("Cannot calculate a percentile of no values.")

    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


async def prepare_questions(
    questions: list[GroundTruthQuestion],
) -> list[PreparedQuestion]:
    """Embed every query once so embedding latency is outside the benchmark."""
    embedding_service = EmbeddingService()
    prepared: list[PreparedQuestion] = []

    for question in questions:
        prepared.append(
            PreparedQuestion(
                ground_truth=question,
                embedding=await embedding_service.embed_text(question.question),
            )
        )

    return prepared


async def evaluate_question(
    vector_queries: VectorQueries,
    prepared: PreparedQuestion,
    candidate_limit: int,
) -> tuple[QuestionEvaluation, float]:
    """Run one timed MariaDB semantic search and evaluate the article ranking."""
    started = time.perf_counter()
    results = await vector_queries.semantic_search(
        embedding=prepared.embedding,
        limit=candidate_limit,
    )
    latency_ms = (time.perf_counter() - started) * 1000.0

    unique_titles = unique_article_titles([item.article_title for item in results])
    retrieved_titles = unique_titles[: max(DEFAULT_K_VALUES)]
    rank, matched_title = find_relevant_result(
        retrieved_titles,
        prepared.ground_truth.relevant_titles,
    )

    evaluation = QuestionEvaluation(
        question_id=prepared.ground_truth.question_id,
        question=prepared.ground_truth.question,
        relevant_titles=prepared.ground_truth.relevant_titles,
        retrieved_titles=tuple(retrieved_titles),
        first_relevant_rank=rank,
        matched_title=matched_title,
        candidate_chunks_examined=len(results),
        unique_articles_found=len(unique_titles),
    )
    return evaluation, latency_ms


async def run_pass(
    vector_queries: VectorQueries,
    prepared_questions: list[PreparedQuestion],
    candidate_limit: int,
    pass_number: int,
) -> PassResult:
    """Run one complete measured pass over the full query set."""
    evaluations: list[QuestionEvaluation] = []
    timings: list[QueryTiming] = []
    latencies: list[float] = []

    for prepared in prepared_questions:
        evaluation, latency_ms = await evaluate_question(
            vector_queries,
            prepared,
            candidate_limit,
        )
        evaluations.append(evaluation)
        latencies.append(latency_ms)
        timings.append(
            QueryTiming(
                question_id=evaluation.question_id,
                latency_ms=latency_ms,
                first_relevant_rank=evaluation.first_relevant_rank,
            )
        )

    return PassResult(
        pass_number=pass_number,
        mean_query_ms=statistics.mean(latencies),
        median_query_ms=statistics.median(latencies),
        p95_query_ms=percentile(latencies, 0.95),
        stddev_query_ms=(statistics.stdev(latencies) if len(latencies) > 1 else 0.0),
        recall_at_10=calculate_recall_at_k(evaluations, 10),
        mrr=calculate_mrr(evaluations),
        timings=tuple(timings),
    )


async def run(*, measured_passes: int, warmup_passes: int) -> Path:
    """Run the repeated full-query benchmark and write a JSON artifact."""
    if measured_passes <= 0:
        raise ValueError("Measured passes must be greater than zero.")
    if warmup_passes < 0:
        raise ValueError("Warm-up passes cannot be negative.")

    questions = load_ground_truth(GROUND_TRUTH_PATH)
    await validate_ground_truth_titles(questions=questions)
    prepared = await prepare_questions(questions)
    article_count, vector_count = await load_corpus_statistics()
    environment = await collect_environment()

    candidate_limit = min(
        vector_count,
        max(
            max(DEFAULT_K_VALUES) * DEFAULT_CANDIDATE_MULTIPLIER,
            MINIMUM_CANDIDATE_LIMIT,
        ),
    )

    try:
        async with database_manager.session() as session:
            vector_queries = VectorQueries(session)

            for _ in range(warmup_passes):
                for item in prepared:
                    await vector_queries.semantic_search(
                        embedding=item.embedding,
                        limit=candidate_limit,
                    )

            pass_results = [
                await run_pass(
                    vector_queries,
                    prepared,
                    candidate_limit,
                    pass_number,
                )
                for pass_number in range(1, measured_passes + 1)
            ]
    finally:
        await database_manager.dispose()

    all_latencies = [
        timing.latency_ms
        for pass_result in pass_results
        for timing in pass_result.timings
    ]
    pass_means = [item.mean_query_ms for item in pass_results]

    study = GroundTruthLatencyStudy(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        questions=len(prepared),
        corpus_articles=article_count,
        corpus_vectors=vector_count,
        candidate_limit=candidate_limit,
        warmup_passes=warmup_passes,
        measured_passes=measured_passes,
        total_measured_queries=len(all_latencies),
        aggregate_mean_query_ms=statistics.mean(all_latencies),
        aggregate_median_query_ms=statistics.median(all_latencies),
        aggregate_p95_query_ms=percentile(all_latencies, 0.95),
        between_pass_mean_stddev_ms=(
            statistics.stdev(pass_means) if len(pass_means) > 1 else 0.0
        ),
        mean_recall_at_10=statistics.mean(item.recall_at_10 for item in pass_results),
        mean_mrr=statistics.mean(item.mrr for item in pass_results),
        passes=tuple(pass_results),
    )

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"ground_truth_latency_{timestamp}.json"
    output_path.write_text(
        json.dumps(asdict(study), indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Questions: {study.questions}")
    print(f"Measured passes: {study.measured_passes}")
    print(f"Measured queries: {study.total_measured_queries}")
    print(f"Mean: {study.aggregate_mean_query_ms:.3f} ms")
    print(f"Median: {study.aggregate_median_query_ms:.3f} ms")
    print(f"P95: {study.aggregate_p95_query_ms:.3f} ms")
    print(f"Between-pass mean stddev: {study.between_pass_mean_stddev_ms:.3f} ms")
    print(f"Recall@10: {study.mean_recall_at_10:.3f}")
    print(f"MRR: {study.mean_mrr:.3f}")
    print(f"Saved results to {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark all ground-truth queries across repeated passes."
    )
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    parser.add_argument(
        "--warmup-passes",
        type=int,
        default=DEFAULT_WARMUP_PASSES,
    )
    return parser.parse_args()


async def async_main() -> None:
    """Run from CLI."""
    args = parse_args()
    await run(
        measured_passes=args.passes,
        warmup_passes=args.warmup_passes,
    )


if __name__ == "__main__":
    asyncio.run(async_main())
