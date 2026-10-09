"""Inspect exact article-level rankings for difficult recall questions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypedDict

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService

GROUND_TRUTH_PATH = Path("data/ground_truth/questions.jsonl")

TARGET_IDS = {
    "q008",
    "q018",
    "q023",
    "q025",
}

LIMIT = 25


class GroundTruthPayload(TypedDict):
    """Represent one raw ground-truth JSON entry."""

    id: str
    question: str
    relevant_titles: list[str]


def load_questions() -> list[GroundTruthPayload]:
    """Load selected diagnostic questions."""
    questions: list[GroundTruthPayload] = []

    for line in GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        payload: GroundTruthPayload = json.loads(stripped)

        if payload["id"] in TARGET_IDS:
            questions.append(payload)

    return questions


async def run() -> None:
    """Print article rankings for difficult queries."""
    questions = load_questions()

    embedding_service = EmbeddingService()

    try:
        async with database_manager.session() as session:
            vector_queries = VectorQueries(session)

            for question in questions:
                question_id = question["id"]
                question_text = question["question"]

                relevant_titles = set(question["relevant_titles"])

                embedding = await embedding_service.embed_text(question_text)

                results = await vector_queries.article_search(
                    embedding=embedding,
                    limit=LIMIT,
                )

                print()
                print("=" * 90)
                print(f"{question_id}: {question_text}")
                print(f"Expected: {', '.join(sorted(relevant_titles))}")
                print("=" * 90)

                for rank, result in enumerate(
                    results,
                    start=1,
                ):
                    marker = (
                        " <-- EXPECTED"
                        if result.article_title in relevant_titles
                        else ""
                    )

                    print(
                        f"{rank:>2}. "
                        f"{result.distance:.6f}  "
                        f"{result.article_title}"
                        f"{marker}"
                    )

    finally:
        await database_manager.dispose()


if __name__ == "__main__":
    asyncio.run(run())
