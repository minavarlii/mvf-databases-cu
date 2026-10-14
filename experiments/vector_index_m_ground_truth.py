"""Evaluate MariaDB VECTOR INDEX M values on the full ground-truth set."""

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

INDEX_NAME = "ix_chunks_embedding"
DEFAULT_M_VALUES = (4, 8, 16, 32)
PRODUCTION_M = 8
DEFAULT_MAX_K = max(DEFAULT_K_VALUES)
RESULTS_DIRECTORY = Path("experiments/results")

DROP_INDEX_SQL = f"""
DROP INDEX IF EXISTS {INDEX_NAME}
ON chunks
"""


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """Ground-truth question paired with a precomputed query embedding."""

    ground_truth: GroundTruthQuestion
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class MSweepResult:
    """Metrics collected for one MariaDB VECTOR INDEX M value."""

    m: int
    build_time_ms: float
    mean_query_ms: float
    median_query_ms: float
    p95_query_ms: float
    min_query_ms: float
    max_query_ms: float
    recall_at_1: float | None
    recall_at_3: float | None
    recall_at_5: float | None
    recall_at_10: float | None
    mrr: float
    misses_at_10: int
    evaluations: tuple[QuestionEvaluation, ...]


def create_index_sql(m_value: int) -> str:
    """Build CREATE VECTOR INDEX SQL for one M value."""
    return f"""
CREATE VECTOR INDEX {INDEX_NAME}
ON chunks (embedding)
M = {m_value}
DISTANCE = cosine
"""


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile from non-empty values."""
    if not values:
        raise ValueError("Cannot calculate percentile of an empty sample.")

    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


async def rebuild_index(
    session: AsyncSession,
    *,
    m_value: int,
) -> float:
    """Drop and rebuild the native MariaDB vector index."""
    await session.execute(text(DROP_INDEX_SQL))

    started = time.perf_counter()
    await session.execute(text(create_index_sql(m_value)))
    build_time_ms = (time.perf_counter() - started) * 1000

    await session.execute(text("ANALYZE TABLE chunks"))

    return build_time_ms


async def prepare_questions(
    questions: list[GroundTruthQuestion],
) -> list[PreparedQuestion]:
    """Embed every ground-truth question once for fair cross-M comparison."""
    embedding_service = EmbeddingService()
    prepared: list[PreparedQuestion] = []

    print("Precomputing query embeddings...")

    for index, question in enumerate(questions, start=1):
        embedding = await embedding_service.embed_text(question.question)
        prepared.append(
            PreparedQuestion(
                ground_truth=question,
                embedding=embedding,
            )
        )
        print(f"[{index}/{len(questions)}] {question.question_id}")

    return prepared


async def run_search(
    vector_queries: VectorQueries,
    *,
    prepared_question: PreparedQuestion,
    max_k: int,
    candidate_limit: int,
) -> tuple[QuestionEvaluation, float]:
    """Run one production semantic search and evaluate the result."""
    started = time.perf_counter()
    results = await vector_queries.semantic_search(
        embedding=prepared_question.embedding,
        limit=candidate_limit,
    )
    query_ms = (time.perf_counter() - started) * 1000

    unique_titles = unique_article_titles([result.article_title for result in results])
    retrieved_titles = unique_titles[:max_k]

    rank, matched_title = find_relevant_result(
        retrieved_titles,
        prepared_question.ground_truth.relevant_titles,
    )

    evaluation = QuestionEvaluation(
        question_id=prepared_question.ground_truth.question_id,
        question=prepared_question.ground_truth.question,
        relevant_titles=prepared_question.ground_truth.relevant_titles,
        retrieved_titles=tuple(retrieved_titles),
        first_relevant_rank=rank,
        matched_title=matched_title,
        candidate_chunks_examined=len(results),
        unique_articles_found=len(unique_titles),
    )

    return evaluation, query_ms


async def warm_up(
    vector_queries: VectorQueries,
    *,
    prepared_questions: list[PreparedQuestion],
    candidate_limit: int,
) -> None:
    """Warm the index and buffer pool without recording measurements."""
    for prepared_question in prepared_questions:
        await vector_queries.semantic_search(
            embedding=prepared_question.embedding,
            limit=candidate_limit,
        )


def recall_for_k(
    evaluations: list[QuestionEvaluation],
    *,
    k: int,
    max_k: int,
) -> float | None:
    """Return Recall@K when K was included in this evaluation."""
    if k > max_k:
        return None

    return calculate_recall_at_k(evaluations, k)


async def evaluate_m(
    session: AsyncSession,
    *,
    m_value: int,
    prepared_questions: list[PreparedQuestion],
    max_k: int,
    candidate_limit: int,
) -> MSweepResult:
    """Rebuild one M value and evaluate all ground-truth questions."""
    print()
    print("=" * 78)
    print(f"M = {m_value}")
    print("=" * 78)

    print("Rebuilding vector index...")
    build_time_ms = await rebuild_index(session, m_value=m_value)
    print(f"Build time: {build_time_ms:.3f} ms")

    vector_queries = VectorQueries(session)

    print("Warming up all ground-truth queries...")
    await warm_up(
        vector_queries,
        prepared_questions=prepared_questions,
        candidate_limit=candidate_limit,
    )

    evaluations: list[QuestionEvaluation] = []
    latency_samples: list[float] = []

    print("Running measured ground-truth evaluation...")

    for index, prepared_question in enumerate(prepared_questions, start=1):
        evaluation, query_ms = await run_search(
            vector_queries,
            prepared_question=prepared_question,
            max_k=max_k,
            candidate_limit=candidate_limit,
        )

        evaluations.append(evaluation)
        latency_samples.append(query_ms)

        status = (
            (f"rank={evaluation.first_relevant_rank} ({evaluation.matched_title})")
            if evaluation.first_relevant_rank is not None
            else "MISS"
        )

        print(
            f"[{index}/{len(prepared_questions)}] "
            f"{evaluation.question_id}: {status} "
            f"[{query_ms:.3f} ms]"
        )

    result = MSweepResult(
        m=m_value,
        build_time_ms=build_time_ms,
        mean_query_ms=statistics.mean(latency_samples),
        median_query_ms=statistics.median(latency_samples),
        p95_query_ms=percentile(latency_samples, 0.95),
        min_query_ms=min(latency_samples),
        max_query_ms=max(latency_samples),
        recall_at_1=recall_for_k(evaluations, k=1, max_k=max_k),
        recall_at_3=recall_for_k(evaluations, k=3, max_k=max_k),
        recall_at_5=recall_for_k(evaluations, k=5, max_k=max_k),
        recall_at_10=recall_for_k(evaluations, k=10, max_k=max_k),
        mrr=calculate_mrr(evaluations),
        misses_at_10=sum(
            1
            for evaluation in evaluations
            if (
                evaluation.first_relevant_rank is None
                or evaluation.first_relevant_rank > 10
            )
        ),
        evaluations=tuple(evaluations),
    )

    print()
    print(
        f"M={result.m}: mean={result.mean_query_ms:.3f} ms, "
        f"median={result.median_query_ms:.3f} ms, "
        f"p95={result.p95_query_ms:.3f} ms"
    )

    for k in DEFAULT_K_VALUES:
        value = getattr(result, f"recall_at_{k}")
        if value is not None:
            print(f"Recall@{k}: {value:.3f} ({value * 100:.1f}%)")

    print(f"MRR:       {result.mrr:.3f}")
    print(f"Misses@10: {result.misses_at_10}")

    return result


async def run(
    *,
    ground_truth_path: Path,
    max_k: int,
    candidate_multiplier: int,
    m_values: tuple[int, ...],
) -> None:
    """Run the complete full-ground-truth M sweep."""
    if max_k < 10:
        raise ValueError("max-k must be at least 10 for this experiment.")

    if candidate_multiplier <= 0:
        raise ValueError("candidate-multiplier must be greater than zero.")

    questions = load_ground_truth(ground_truth_path)
    await validate_ground_truth_titles(questions=questions)

    article_count, vector_count = await load_corpus_statistics()
    candidate_limit = min(
        vector_count,
        max(
            max_k * candidate_multiplier,
            MINIMUM_CANDIDATE_LIMIT,
        ),
    )

    prepared_questions = await prepare_questions(questions)

    print()
    print("MariaDB VECTOR INDEX full ground-truth M sweep")
    print()
    print(f"Articles:             {article_count}")
    print(f"Vectors:              {vector_count}")
    print(f"Questions:            {len(questions)}")
    print(f"Max K:                {max_k}")
    print(f"Candidate pool:       {candidate_limit} chunks")
    print(f"M values:             {', '.join(map(str, m_values))}")
    print(f"Production M restore: {PRODUCTION_M}")

    results: list[MSweepResult] = []

    try:
        async with database_manager.session() as session:
            for m_value in m_values:
                result = await evaluate_m(
                    session,
                    m_value=m_value,
                    prepared_questions=prepared_questions,
                    max_k=max_k,
                    candidate_limit=candidate_limit,
                )
                results.append(result)

    finally:
        print()
        print(f"Restoring production M = {PRODUCTION_M}...")

        try:
            async with database_manager.session() as session:
                restore_time_ms = await rebuild_index(
                    session,
                    m_value=PRODUCTION_M,
                )

            print(f"Production index restored in {restore_time_ms:.3f} ms.")
        finally:
            await database_manager.dispose()

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"vector_index_m_ground_truth_{timestamp}.json"

    payload = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "corpus": {
            "articles": article_count,
            "vectors": vector_count,
            "questions": len(questions),
        },
        "retrieval_methodology": {
            "ground_truth_path": str(ground_truth_path),
            "max_k": max_k,
            "candidate_multiplier": candidate_multiplier,
            "candidate_limit": candidate_limit,
            "query_embeddings_precomputed_once": True,
            "warmup_passes_per_m": 1,
            "measured_passes_per_m": 1,
            "latency_scope": "MariaDB semantic_search only",
        },
        "vector_index": {
            "index_name": INDEX_NAME,
            "distance": "cosine",
            "m_values": list(m_values),
            "production_m": PRODUCTION_M,
        },
        "results": [asdict(result) for result in results],
    }

    output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("Final comparison")
    print("-" * 110)
    print(
        "M    Build ms    Mean ms   Median ms    P95 ms   "
        "R@1     R@3     R@5    R@10     MRR   Misses@10"
    )
    print("-" * 110)

    for result in results:

        def fmt_recall(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.3f}"

        print(
            f"{result.m:<4} "
            f"{result.build_time_ms:>10.3f} "
            f"{result.mean_query_ms:>10.3f} "
            f"{result.median_query_ms:>11.3f} "
            f"{result.p95_query_ms:>9.3f} "
            f"{fmt_recall(result.recall_at_1):>7} "
            f"{fmt_recall(result.recall_at_3):>7} "
            f"{fmt_recall(result.recall_at_5):>7} "
            f"{fmt_recall(result.recall_at_10):>7} "
            f"{result.mrr:>7.3f} "
            f"{result.misses_at_10:>10}"
        )

    print()
    print(f"Saved result to {output_path}")
    print(f"Production vector index restored to M={PRODUCTION_M}.")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate MariaDB VECTOR INDEX M values against the "
            "full article-level ground-truth set."
        )
    )

    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=GROUND_TRUTH_PATH,
        help="Path to the JSONL ground-truth dataset.",
    )
    parser.add_argument(
        "--max-k",
        type=int,
        default=DEFAULT_MAX_K,
        help="Maximum article-level retrieval cutoff.",
    )
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=DEFAULT_CANDIDATE_MULTIPLIER,
        help="Chunk candidate pool multiplier relative to max-k.",
    )
    parser.add_argument(
        "--m-values",
        type=int,
        nargs="+",
        default=list(DEFAULT_M_VALUES),
        help="MariaDB VECTOR INDEX M values to evaluate.",
    )

    return parser.parse_args()


async def main() -> None:
    """Run command."""
    arguments = parse_arguments()
    m_values = tuple(arguments.m_values)

    if not m_values:
        raise ValueError("At least one M value is required.")

    for m_value in m_values:
        if not 3 <= m_value <= 200:
            raise ValueError("MariaDB VECTOR INDEX M must be between 3 and 200.")

    await run(
        ground_truth_path=arguments.ground_truth,
        max_k=arguments.max_k,
        candidate_multiplier=arguments.candidate_multiplier,
        m_values=m_values,
    )


if __name__ == "__main__":
    asyncio.run(main())
