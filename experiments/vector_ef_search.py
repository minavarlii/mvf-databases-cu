"""Evaluate MariaDB mhnsw_ef_search over the full ground-truth set."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

DEFAULT_EF_VALUES = (200, 400, 800, 1600)
PRODUCTION_EF_SEARCH = 20
DEFAULT_REPEATS = 3
DEFAULT_WARMUP_ROUNDS = 1
RESULTS_DIRECTORY = Path("experiments/results")

SET_EF_SQL_BY_VALUE = {
    20: "SET SESSION mhnsw_ef_search = 20",
    200: "SET SESSION mhnsw_ef_search = 200",
    400: "SET SESSION mhnsw_ef_search = 400",
    800: "SET SESSION mhnsw_ef_search = 800",
    1600: "SET SESSION mhnsw_ef_search = 1600",
}


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """Ground-truth question paired with a precomputed embedding."""

    ground_truth: GroundTruthQuestion
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class RepeatResult:
    """Quality and latency metrics for one complete 40-question pass."""

    repeat: int
    mean_query_ms: float
    median_query_ms: float
    p95_query_ms: float
    stddev_query_ms: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    misses_at_10: int


@dataclass(frozen=True, slots=True)
class EfSearchResult:
    """Aggregate repeated measurements for one ef_search setting."""

    ef_search: int
    repeats: tuple[RepeatResult, ...]
    aggregate_mean_query_ms: float
    aggregate_p95_query_ms: float
    aggregate_stddev_query_ms: float
    mean_recall_at_10: float
    min_recall_at_10: float
    max_recall_at_10: float
    mean_mrr: float


@dataclass(frozen=True, slots=True)
class EfSearchStudy:
    """Complete runtime HNSW tuning study."""

    executed_at: str
    environment: EnvironmentMetadata
    questions: int
    corpus_articles: int
    corpus_vectors: int
    candidate_limit: int
    warmup_rounds: int
    repeats: int
    results: tuple[EfSearchResult, ...]


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile from a non-empty sample."""
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def ef_sql(value: int) -> str:
    """Return a static SET statement for a supported ef_search value."""
    try:
        return SET_EF_SQL_BY_VALUE[value]
    except KeyError as exc:
        supported = ", ".join(str(item) for item in SET_EF_SQL_BY_VALUE)
        raise ValueError(
            f"Unsupported mhnsw_ef_search value {value}; use one of {supported}."
        ) from exc


async def set_ef_search(session: AsyncSession, value: int) -> None:
    """Set the MariaDB session-level HNSW candidate-search parameter."""
    await session.execute(text(ef_sql(value)))


async def prepare_questions(
    questions: list[GroundTruthQuestion],
) -> list[PreparedQuestion]:
    """Embed each ground-truth question once before database timing."""
    service = EmbeddingService()
    prepared: list[PreparedQuestion] = []

    for question in questions:
        prepared.append(
            PreparedQuestion(
                ground_truth=question,
                embedding=await service.embed_text(question.question),
            )
        )

    return prepared


async def evaluate_question(
    vector_queries: VectorQueries,
    prepared: PreparedQuestion,
    candidate_limit: int,
) -> tuple[QuestionEvaluation, float]:
    """Run one ANN query and evaluate article-level relevance."""
    started = time.perf_counter()
    results = await vector_queries.semantic_search(
        embedding=prepared.embedding,
        limit=candidate_limit,
    )
    query_ms = (time.perf_counter() - started) * 1000

    unique_titles = unique_article_titles([result.article_title for result in results])
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

    return evaluation, query_ms


async def warm_up(
    vector_queries: VectorQueries,
    prepared_questions: list[PreparedQuestion],
    candidate_limit: int,
    rounds: int,
) -> None:
    """Warm the index and buffer pool without recording samples."""
    for _ in range(rounds):
        for prepared in prepared_questions:
            await vector_queries.semantic_search(
                embedding=prepared.embedding,
                limit=candidate_limit,
            )


async def run_repeat(
    vector_queries: VectorQueries,
    prepared_questions: list[PreparedQuestion],
    candidate_limit: int,
    repeat: int,
) -> RepeatResult:
    """Run one complete ground-truth pass."""
    evaluations: list[QuestionEvaluation] = []
    latencies: list[float] = []

    for prepared in prepared_questions:
        evaluation, latency = await evaluate_question(
            vector_queries,
            prepared,
            candidate_limit,
        )
        evaluations.append(evaluation)
        latencies.append(latency)

    return RepeatResult(
        repeat=repeat,
        mean_query_ms=statistics.mean(latencies),
        median_query_ms=statistics.median(latencies),
        p95_query_ms=percentile(latencies, 0.95),
        stddev_query_ms=(statistics.stdev(latencies) if len(latencies) > 1 else 0.0),
        recall_at_1=calculate_recall_at_k(evaluations, 1),
        recall_at_3=calculate_recall_at_k(evaluations, 3),
        recall_at_5=calculate_recall_at_k(evaluations, 5),
        recall_at_10=calculate_recall_at_k(evaluations, 10),
        mrr=calculate_mrr(evaluations),
        misses_at_10=sum(
            1
            for evaluation in evaluations
            if evaluation.first_relevant_rank is None
            or evaluation.first_relevant_rank > 10
        ),
    )


async def evaluate_setting(
    session: AsyncSession,
    prepared_questions: list[PreparedQuestion],
    candidate_limit: int,
    ef_search: int,
    warmup_rounds: int,
    repeats: int,
) -> EfSearchResult:
    """Evaluate one session-level ef_search value repeatedly."""
    await set_ef_search(session, ef_search)
    vector_queries = VectorQueries(session)

    await warm_up(
        vector_queries,
        prepared_questions,
        candidate_limit,
        warmup_rounds,
    )

    repeat_results = [
        await run_repeat(
            vector_queries,
            prepared_questions,
            candidate_limit,
            repeat,
        )
        for repeat in range(1, repeats + 1)
    ]

    mean_latencies = [item.mean_query_ms for item in repeat_results]
    p95_latencies = [item.p95_query_ms for item in repeat_results]
    recall_values = [item.recall_at_10 for item in repeat_results]
    mrr_values = [item.mrr for item in repeat_results]

    return EfSearchResult(
        ef_search=ef_search,
        repeats=tuple(repeat_results),
        aggregate_mean_query_ms=statistics.mean(mean_latencies),
        aggregate_p95_query_ms=statistics.mean(p95_latencies),
        aggregate_stddev_query_ms=(
            statistics.stdev(mean_latencies) if len(mean_latencies) > 1 else 0.0
        ),
        mean_recall_at_10=statistics.mean(recall_values),
        min_recall_at_10=min(recall_values),
        max_recall_at_10=max(recall_values),
        mean_mrr=statistics.mean(mrr_values),
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate MariaDB mhnsw_ef_search quality/latency over ground truth."
        )
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=DEFAULT_REPEATS,
    )
    parser.add_argument(
        "--warmup-rounds",
        type=int,
        default=DEFAULT_WARMUP_ROUNDS,
    )
    return parser.parse_args()


async def async_main() -> None:
    """Run the complete ef_search study and persist JSON output."""
    args = parse_args()
    if args.repeats <= 0:
        raise ValueError("Repeats must be greater than zero.")
    if args.warmup_rounds < 0:
        raise ValueError("Warm-up rounds cannot be negative.")

    questions = load_ground_truth(GROUND_TRUTH_PATH)
    await validate_ground_truth_titles(questions=questions)
    prepared_questions = await prepare_questions(questions)
    corpus_articles, corpus_vectors = await load_corpus_statistics()
    environment = await collect_environment()

    candidate_limit = max(
        MINIMUM_CANDIDATE_LIMIT,
        max(DEFAULT_K_VALUES) * DEFAULT_CANDIDATE_MULTIPLIER,
    )

    results: list[EfSearchResult] = []

    try:
        async with database_manager.session() as session:
            try:
                for ef_search in DEFAULT_EF_VALUES:
                    print(f"Evaluating mhnsw_ef_search={ef_search}...")
                    result = await evaluate_setting(
                        session,
                        prepared_questions,
                        candidate_limit,
                        ef_search,
                        args.warmup_rounds,
                        args.repeats,
                    )
                    results.append(result)
                    print(
                        f"  mean={result.aggregate_mean_query_ms:.3f} ms  "
                        f"R@10={result.mean_recall_at_10:.3f}  "
                        f"MRR={result.mean_mrr:.3f}"
                    )
            finally:
                await set_ef_search(session, PRODUCTION_EF_SEARCH)
    finally:
        await database_manager.dispose()

    study = EfSearchStudy(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        questions=len(questions),
        corpus_articles=corpus_articles,
        corpus_vectors=corpus_vectors,
        candidate_limit=candidate_limit,
        warmup_rounds=args.warmup_rounds,
        repeats=args.repeats,
        results=tuple(results),
    )

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"vector_ef_search_{timestamp}.json"
    output_path.write_text(
        json.dumps(asdict(study), indent=2),
        encoding="utf-8",
    )
    print(f"Saved results to {output_path}")


def main() -> None:
    """Run the asynchronous entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
