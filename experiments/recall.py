"""Evaluate semantic retrieval quality using article-level Recall@K."""

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

GROUND_TRUTH_PATH = Path("data/ground_truth/questions.jsonl")

RESULTS_DIRECTORY = Path("experiments/results")

DEFAULT_K_VALUES = (
    1,
    3,
    5,
    10,
)

DEFAULT_CANDIDATE_MULTIPLIER = 20

MINIMUM_CANDIDATE_LIMIT = 200


@dataclass(frozen=True, slots=True)
class GroundTruthQuestion:
    """Represent one retrieval-evaluation question."""

    question_id: str
    question: str
    relevant_titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuestionEvaluation:
    """Represent retrieval results for one question."""

    question_id: str
    question: str
    relevant_titles: tuple[str, ...]
    retrieved_titles: tuple[str, ...]
    first_relevant_rank: int | None
    matched_title: str | None
    candidate_chunks_examined: int
    unique_articles_found: int


@dataclass(frozen=True, slots=True)
class RecallResult:
    """Represent the complete retrieval-quality experiment."""

    evaluated_at: str
    questions: int
    max_k: int
    candidate_limit: int
    corpus_articles: int
    corpus_vectors: int
    recall_at_1: float | None
    recall_at_3: float | None
    recall_at_5: float | None
    recall_at_10: float | None
    mrr: float
    misses_at_max_k: int
    evaluations: tuple[QuestionEvaluation, ...]


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate MariaDB semantic retrieval "
            "using an article-level ground-truth set."
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
        default=max(DEFAULT_K_VALUES),
        help="Maximum article-level retrieval cutoff.",
    )

    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=DEFAULT_CANDIDATE_MULTIPLIER,
        help=("Chunk candidate pool multiplier relative to max-k."),
    )

    return parser.parse_args()


def load_ground_truth(
    path: Path,
) -> list[GroundTruthQuestion]:
    """Load ground-truth questions from JSONL."""
    questions: list[GroundTruthQuestion] = []

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()

        if not stripped:
            continue

        payload = json.loads(stripped)

        question_id = str(payload["id"]).strip()

        question = str(payload["question"]).strip()

        relevant_titles = tuple(
            str(title).strip()
            for title in payload["relevant_titles"]
            if str(title).strip()
        )

        if not question_id:
            raise ValueError(f"Missing question id at line {line_number}.")

        if not question:
            raise ValueError(f"Missing question text at line {line_number}.")

        if not relevant_titles:
            raise ValueError(f"No relevant titles at line {line_number}.")

        questions.append(
            GroundTruthQuestion(
                question_id=question_id,
                question=question,
                relevant_titles=relevant_titles,
            )
        )

    if not questions:
        raise ValueError("Ground-truth dataset is empty.")

    return questions


def unique_article_titles(
    titles: list[str],
) -> list[str]:
    """Remove duplicate titles while preserving ranking."""
    return list(dict.fromkeys(titles))


def find_relevant_result(
    retrieved_titles: list[str],
    relevant_titles: tuple[str, ...],
) -> tuple[int | None, str | None]:
    """Find first relevant article and its rank."""
    relevant_set = set(relevant_titles)

    for rank, title in enumerate(
        retrieved_titles,
        start=1,
    ):
        if title in relevant_set:
            return (
                rank,
                title,
            )

    return (
        None,
        None,
    )


def calculate_recall_at_k(
    evaluations: list[QuestionEvaluation],
    k: int,
) -> float:
    """Calculate query-level Recall@K."""
    successful = sum(
        1
        for evaluation in evaluations
        if (
            evaluation.first_relevant_rank is not None
            and evaluation.first_relevant_rank <= k
        )
    )

    return successful / len(evaluations)


def calculate_mrr(
    evaluations: list[QuestionEvaluation],
) -> float:
    """Calculate Mean Reciprocal Rank."""
    reciprocal_ranks = [
        (
            1.0 / evaluation.first_relevant_rank
            if evaluation.first_relevant_rank is not None
            else 0.0
        )
        for evaluation in evaluations
    ]

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


async def validate_ground_truth_titles(
    *,
    questions: list[GroundTruthQuestion],
) -> None:
    """Ensure all referenced articles exist in MariaDB."""
    expected_titles = {
        title for question in questions for title in question.relevant_titles
    }

    async with database_manager.session() as session:
        result = await session.execute(
            select(Article.title).where(Article.title.in_(expected_titles))
        )

        existing_titles = set(result.scalars().all())

    missing_titles = sorted(expected_titles - existing_titles)

    if missing_titles:
        formatted = "\n".join(f"- {title}" for title in missing_titles)

        raise ValueError(
            "Ground truth references articles that "
            "do not exist in the database:\n"
            f"{formatted}"
        )


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
    candidate_limit: int,
) -> QuestionEvaluation:
    """Evaluate one ground-truth question."""
    embedding = await embedding_service.embed_text(question.question)

    results = await vector_queries.semantic_search(
        embedding=embedding,
        limit=candidate_limit,
    )

    unique_titles = unique_article_titles([result.article_title for result in results])

    retrieved_titles = unique_titles[:max_k]

    rank, matched_title = find_relevant_result(
        retrieved_titles,
        question.relevant_titles,
    )

    return QuestionEvaluation(
        question_id=question.question_id,
        question=question.question,
        relevant_titles=(question.relevant_titles),
        retrieved_titles=tuple(retrieved_titles),
        first_relevant_rank=rank,
        matched_title=matched_title,
        candidate_chunks_examined=len(results),
        unique_articles_found=len(unique_titles),
    )


def recall_for_k(
    *,
    evaluations: list[QuestionEvaluation],
    k: int,
    max_k: int,
) -> float | None:
    """Return Recall@K when K was evaluated."""
    if k > max_k:
        return None

    return calculate_recall_at_k(
        evaluations,
        k,
    )


async def run(
    *,
    ground_truth_path: Path,
    max_k: int,
    candidate_multiplier: int,
) -> RecallResult:
    """Run retrieval-quality evaluation."""
    if max_k <= 0:
        raise ValueError("max-k must be greater than zero.")

    if candidate_multiplier <= 0:
        raise ValueError("candidate-multiplier must be greater than zero.")

    questions = load_ground_truth(ground_truth_path)

    await validate_ground_truth_titles(questions=questions)

    article_count, vector_count = await load_corpus_statistics()
    environment = await collect_environment()

    candidate_limit = min(
        vector_count,
        max(
            max_k * candidate_multiplier,
            MINIMUM_CANDIDATE_LIMIT,
        ),
    )

    embedding_service = EmbeddingService()

    evaluations: list[QuestionEvaluation] = []

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
                    candidate_limit=(candidate_limit),
                )

                evaluations.append(evaluation)

                status = (
                    (
                        "rank="
                        f"{evaluation.first_relevant_rank} "
                        f"({evaluation.matched_title})"
                    )
                    if evaluation.first_relevant_rank is not None
                    else "MISS"
                )

                print(f"[{index}/{len(questions)}] {question.question_id}: {status}")
    finally:
        await database_manager.dispose()

    result = RecallResult(
        evaluated_at=datetime.now(UTC).isoformat(),
        questions=len(evaluations),
        max_k=max_k,
        candidate_limit=(candidate_limit),
        corpus_articles=(article_count),
        corpus_vectors=(vector_count),
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
        mrr=calculate_mrr(evaluations),
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

    output_path = RESULTS_DIRECTORY / f"recall_{timestamp}.json"

    output_path.write_text(
        json.dumps(
            {"environment": asdict(environment), **asdict(result)},
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Corpus articles: {result.corpus_articles}")
    print(f"Corpus vectors:  {result.corpus_vectors}")
    print(f"Candidate pool:  {result.candidate_limit} chunks")
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
    """Run the recall experiment."""
    arguments = parse_arguments()

    await run(
        ground_truth_path=(arguments.ground_truth),
        max_k=arguments.max_k,
        candidate_multiplier=(arguments.candidate_multiplier),
    )


if __name__ == "__main__":
    asyncio.run(main())
