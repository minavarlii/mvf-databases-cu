"""Evaluate exact article-level semantic retrieval quality."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from backend.app.db import database_manager
from backend.app.db.models import Article, Chunk
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService
from experiments.environment import collect_environment
from experiments.recall import (
    DEFAULT_K_VALUES,
    GROUND_TRUTH_PATH,
    GroundTruthQuestion,
    find_relevant_result,
    load_ground_truth,
    validate_ground_truth_titles,
)

RESULTS_DIRECTORY = Path("experiments/results")


@dataclass(frozen=True, slots=True)
class ArticleQuestionEvaluation:
    """Represent exact article-level retrieval for one question."""

    question_id: str
    question: str
    relevant_titles: tuple[str, ...]
    retrieved_titles: tuple[str, ...]
    first_relevant_rank: int | None
    matched_title: str | None


@dataclass(frozen=True, slots=True)
class ArticleRecallResult:
    """Represent the exact article-level retrieval experiment."""

    evaluated_at: str
    questions: int
    max_k: int
    corpus_articles: int
    corpus_vectors: int
    recall_at_1: float | None
    recall_at_3: float | None
    recall_at_5: float | None
    recall_at_10: float | None
    mrr: float
    misses_at_max_k: int
    evaluations: tuple[ArticleQuestionEvaluation, ...]


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Evaluate exact article-level MariaDB semantic retrieval.")
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
        default=max(DEFAULT_K_VALUES),
        help="Maximum article-level retrieval cutoff.",
    )

    return parser.parse_args()


async def load_corpus_statistics() -> tuple[int, int]:
    """Return article and vector counts."""
    async with database_manager.session() as session:
        article_count = await session.scalar(select(func.count(Article.id)))

        vector_count = await session.scalar(select(func.count(Chunk.id)))

    return (
        int(article_count or 0),
        int(vector_count or 0),
    )


async def evaluate_question(
    *,
    question: GroundTruthQuestion,
    embedding_service: EmbeddingService,
    vector_queries: VectorQueries,
    max_k: int,
) -> ArticleQuestionEvaluation:
    """Evaluate one question using exact article ranking."""
    embedding = await embedding_service.embed_text(question.question)

    results = await vector_queries.article_search(
        embedding=embedding,
        limit=max_k,
    )

    retrieved_titles = [result.article_title for result in results]

    rank, matched_title = find_relevant_result(
        retrieved_titles,
        question.relevant_titles,
    )

    return ArticleQuestionEvaluation(
        question_id=question.question_id,
        question=question.question,
        relevant_titles=question.relevant_titles,
        retrieved_titles=tuple(retrieved_titles),
        first_relevant_rank=rank,
        matched_title=matched_title,
    )


def calculate_article_recall_at_k(
    evaluations: list[ArticleQuestionEvaluation],
    k: int,
) -> float:
    """Calculate query-level article Recall@K."""
    successful = sum(
        1
        for evaluation in evaluations
        if (
            evaluation.first_relevant_rank is not None
            and evaluation.first_relevant_rank <= k
        )
    )

    return successful / len(evaluations)


def calculate_article_mrr(
    evaluations: list[ArticleQuestionEvaluation],
) -> float:
    """Calculate article-level Mean Reciprocal Rank."""
    reciprocal_ranks = [
        (
            1.0 / evaluation.first_relevant_rank
            if evaluation.first_relevant_rank is not None
            else 0.0
        )
        for evaluation in evaluations
    ]

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def recall_for_k(
    *,
    evaluations: list[ArticleQuestionEvaluation],
    k: int,
    max_k: int,
) -> float | None:
    """Return Recall@K when the cutoff was evaluated."""
    if k > max_k:
        return None

    return calculate_article_recall_at_k(
        evaluations,
        k,
    )


async def run(
    *,
    ground_truth_path: Path,
    max_k: int,
) -> ArticleRecallResult:
    """Run exact article-level retrieval evaluation."""
    if max_k <= 0:
        raise ValueError("max-k must be greater than zero.")

    questions = load_ground_truth(ground_truth_path)

    await validate_ground_truth_titles(questions=questions)

    article_count, vector_count = await load_corpus_statistics()
    environment = await collect_environment()

    embedding_service = EmbeddingService()

    evaluations: list[ArticleQuestionEvaluation] = []

    try:
        async with database_manager.session() as session:
            vector_queries = VectorQueries(session)

            for index, question in enumerate(
                questions,
                start=1,
            ):
                evaluation = await evaluate_question(
                    question=question,
                    embedding_service=(embedding_service),
                    vector_queries=(vector_queries),
                    max_k=max_k,
                )

                evaluations.append(evaluation)

                status = (
                    (
                        f"rank="
                        f"{evaluation.first_relevant_rank} "
                        f"({evaluation.matched_title})"
                    )
                    if evaluation.first_relevant_rank is not None
                    else "MISS"
                )

                print(f"[{index}/{len(questions)}] {question.question_id}: {status}")
    finally:
        await database_manager.dispose()

    result = ArticleRecallResult(
        evaluated_at=datetime.now(UTC).isoformat(),
        questions=len(evaluations),
        max_k=max_k,
        corpus_articles=article_count,
        corpus_vectors=vector_count,
        recall_at_1=recall_for_k(
            evaluations=evaluations,
            k=1,
            max_k=max_k,
        ),
        recall_at_3=recall_for_k(
            evaluations=evaluations,
            k=3,
            max_k=max_k,
        ),
        recall_at_5=recall_for_k(
            evaluations=evaluations,
            k=5,
            max_k=max_k,
        ),
        recall_at_10=recall_for_k(
            evaluations=evaluations,
            k=10,
            max_k=max_k,
        ),
        mrr=calculate_article_mrr(evaluations),
        misses_at_max_k=sum(
            1 for evaluation in evaluations if evaluation.first_relevant_rank is None
        ),
        evaluations=tuple(evaluations),
    )

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = RESULTS_DIRECTORY / f"article_recall_{timestamp}.json"

    output_path.write_text(
        json.dumps(
            {"environment": asdict(environment), **asdict(result)},
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Exact article-level retrieval")
    print(f"Corpus articles: {result.corpus_articles}")
    print(f"Corpus vectors:  {result.corpus_vectors}")
    print(f"Questions:       {result.questions}")

    for k in DEFAULT_K_VALUES:
        value = getattr(
            result,
            f"recall_at_{k}",
        )

        if value is not None:
            print(f"Recall@{k}:       {value:.3f} ({value * 100:.1f}%)")

    print(f"MRR:            {result.mrr:.3f}")

    print(f"Misses@{max_k}:      {result.misses_at_max_k}")

    print()
    print(f"Saved result to {output_path}")

    return result


async def main() -> None:
    """Run exact article-level evaluation."""
    arguments = parse_arguments()

    await run(
        ground_truth_path=(arguments.ground_truth),
        max_k=arguments.max_k,
    )


if __name__ == "__main__":
    asyncio.run(main())
