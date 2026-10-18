"""Stress concurrent vector writes, reads, deletes, and retrieval quality."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from backend.app.db import analyze_core_tables, database_manager
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
    load_ground_truth,
    unique_article_titles,
)

RESULTS_DIRECTORY = Path("experiments/results")
TITLE_PREFIX = "MVF concurrency probe"

INSERT_ARTICLE_SQL = """
INSERT INTO articles (
    wikipedia_page_id,
    revision_id,
    title,
    url,
    summary,
    content,
    word_count
)
VALUES (
    :page_id,
    :revision_id,
    :title,
    :url,
    :summary,
    :content,
    :word_count
)
""".strip()

LAST_INSERT_ID_SQL = "SELECT LAST_INSERT_ID()"

INSERT_CHUNK_SQL = """
INSERT INTO chunks (
    article_id,
    chunk_index,
    content,
    token_count,
    embedding
)
VALUES (
    :article_id,
    0,
    :content,
    :token_count,
    VEC_FromText(:embedding)
)
""".strip()

DELETE_PROBE_ARTICLES_SQL = """
DELETE FROM articles
WHERE title LIKE :prefix
""".strip()

COUNT_PROBE_ARTICLES_SQL = """
SELECT COUNT(*)
FROM articles
WHERE title LIKE :prefix
""".strip()

COUNT_ORPHAN_CHUNKS_SQL = """
SELECT COUNT(*)
FROM chunks AS c
LEFT JOIN articles AS a ON a.id = c.article_id
WHERE a.id IS NULL
""".strip()


@dataclass(frozen=True, slots=True)
class RetrievalQuality:
    """Recall summary for one database state."""

    recall_at_10: float
    mrr: float
    misses_at_10: int


@dataclass(frozen=True, slots=True)
class ConcurrencyResult:
    """Persisted vector-concurrency stress result."""

    executed_at: str
    environment: EnvironmentMetadata
    writers: int
    rows_per_writer: int
    rows_inserted: int
    concurrent_queries: int
    write_failures: int
    query_failures: int
    commit_mean_ms: float
    commit_p95_ms: float
    baseline_quality: RetrievalQuality
    post_insert_quality: RetrievalQuality
    post_delete_quality: RetrievalQuality
    recall_at_10_delta_after_insert: float
    recall_at_10_delta_after_delete: float
    probe_rows_after_cleanup: int
    orphan_chunks_after_cleanup: int


def percentile(values: list[float], fraction: float) -> float:
    """Calculate an interpolated percentile."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("At least one value is required.")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def synthetic_embedding(seed: int, dimensions: int = 384) -> list[float]:
    """Build a deterministic sparse unit vector for stress rows."""
    values = [0.0] * dimensions
    values[seed % dimensions] = 1.0
    return values


async def prepare_ground_truth_embeddings() -> list[
    tuple[GroundTruthQuestion, list[float]]
]:
    """Precompute ground-truth embeddings outside measured DB operations."""
    questions = load_ground_truth(GROUND_TRUTH_PATH)
    service = EmbeddingService()
    embeddings = await service.embed_many([item.question for item in questions])
    return list(zip(questions, embeddings, strict=True))


async def evaluate_quality(
    prepared: list[tuple[GroundTruthQuestion, list[float]]],
) -> RetrievalQuality:
    """Evaluate semantic Recall@10 and MRR for the current DB state."""
    candidate_limit = max(
        max(DEFAULT_K_VALUES) * DEFAULT_CANDIDATE_MULTIPLIER,
        MINIMUM_CANDIDATE_LIMIT,
    )
    evaluations: list[QuestionEvaluation] = []

    async with database_manager.session() as session:
        queries = VectorQueries(session)
        for question, embedding in prepared:
            results = await queries.semantic_search(
                embedding=embedding,
                limit=candidate_limit,
            )
            unique_titles = unique_article_titles(
                [result.article_title for result in results]
            )
            retrieved_titles = unique_titles[:10]
            rank, matched_title = find_relevant_result(
                retrieved_titles,
                question.relevant_titles,
            )
            evaluations.append(
                QuestionEvaluation(
                    question_id=question.question_id,
                    question=question.question,
                    relevant_titles=question.relevant_titles,
                    retrieved_titles=tuple(retrieved_titles),
                    first_relevant_rank=rank,
                    matched_title=matched_title,
                    candidate_chunks_examined=len(results),
                    unique_articles_found=len(unique_titles),
                )
            )

    recall = calculate_recall_at_k(evaluations, 10)
    return RetrievalQuality(
        recall_at_10=recall,
        mrr=calculate_mrr(evaluations),
        misses_at_10=sum(
            evaluation.first_relevant_rank is None
            or evaluation.first_relevant_rank > 10
            for evaluation in evaluations
        ),
    )


async def writer_task(
    *,
    writer_number: int,
    rows: int,
    token: str,
) -> tuple[list[float], int]:
    """Insert and commit synthetic vector-bearing rows in one writer session."""
    timings: list[float] = []
    failures = 0

    async with database_manager.session() as session:
        for offset in range(rows):
            row_number = writer_number * rows + offset
            title = f"{TITLE_PREFIX} {token} w{writer_number} r{offset}"
            content = f"Synthetic concurrent vector row {row_number}."
            embedding = json.dumps(synthetic_embedding(row_number))

            try:
                await session.execute(
                    text(INSERT_ARTICLE_SQL),
                    {
                        "page_id": 8_000_000_000 + row_number + int(token[:5], 16),
                        "revision_id": 7_000_000_000
                        + row_number
                        + int(token[5:10], 16),
                        "title": title,
                        "url": f"https://example.invalid/{token}/{writer_number}/{offset}",
                        "summary": "Synthetic concurrency probe",
                        "content": content,
                        "word_count": len(content.split()),
                    },
                )
                article_id = await session.scalar(text(LAST_INSERT_ID_SQL))
                if article_id is None:
                    raise RuntimeError("LAST_INSERT_ID() returned no value.")
                await session.execute(
                    text(INSERT_CHUNK_SQL),
                    {
                        "article_id": int(article_id),
                        "content": content,
                        "token_count": len(content.split()),
                        "embedding": embedding,
                    },
                )
                started = time.perf_counter()
                await session.commit()
                timings.append((time.perf_counter() - started) * 1000.0)
            except Exception:
                failures += 1
                await session.rollback()

    return timings, failures


async def query_task(*, queries_to_run: int, embedding: list[float]) -> int:
    """Run semantic reads while writer sessions are committing rows."""
    failures = 0
    async with database_manager.session() as session:
        queries = VectorQueries(session)
        for _ in range(queries_to_run):
            try:
                await queries.semantic_search(embedding=embedding, limit=10)
            except Exception:
                failures += 1
            await asyncio.sleep(0)
    return failures


async def cleanup_probes(token: str) -> tuple[int, int]:
    """Delete synthetic rows, refresh stats, and return cleanup counts."""
    prefix = f"{TITLE_PREFIX} {token}%"
    async with database_manager.session() as session:
        await session.execute(text(DELETE_PROBE_ARTICLES_SQL), {"prefix": prefix})
        await session.commit()
        await analyze_core_tables(session)
        await session.commit()
        rows = int(
            await session.scalar(text(COUNT_PROBE_ARTICLES_SQL), {"prefix": prefix})
            or 0
        )
        orphans = int(await session.scalar(text(COUNT_ORPHAN_CHUNKS_SQL)) or 0)
    return rows, orphans


def parse_args() -> argparse.Namespace:
    """Parse stress configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writers", type=int, default=2)
    parser.add_argument("--rows-per-writer", type=int, default=25)
    parser.add_argument("--queries", type=int, default=50)
    return parser.parse_args()


async def async_main() -> None:
    """Run the concurrent write/read and retrieval-quality experiment."""
    args = parse_args()
    if args.writers < 2:
        raise ValueError("Use at least two writers for a concurrency probe.")
    if args.rows_per_writer <= 0 or args.queries <= 0:
        raise ValueError("Rows and query count must be positive.")

    token = uuid4().hex
    environment = await collect_environment()
    prepared = await prepare_ground_truth_embeddings()
    baseline = await evaluate_quality(prepared)
    query_embedding = prepared[0][1]

    writer_jobs = [
        asyncio.create_task(
            writer_task(
                writer_number=writer_number,
                rows=args.rows_per_writer,
                token=token,
            )
        )
        for writer_number in range(args.writers)
    ]
    query_job = asyncio.create_task(
        query_task(queries_to_run=args.queries, embedding=query_embedding)
    )

    try:
        writer_results = await asyncio.gather(*writer_jobs)
        query_failures = await query_job
        commit_timings = [timing for item in writer_results for timing in item[0]]
        write_failures = sum(item[1] for item in writer_results)
        if not commit_timings:
            raise RuntimeError("No successful commits were recorded.")

        post_insert = await evaluate_quality(prepared)
        probe_rows, orphans = await cleanup_probes(token)
        post_delete = await evaluate_quality(prepared)
    finally:
        await cleanup_probes(token)

    result = ConcurrencyResult(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        writers=args.writers,
        rows_per_writer=args.rows_per_writer,
        rows_inserted=args.writers * args.rows_per_writer - write_failures,
        concurrent_queries=args.queries,
        write_failures=write_failures,
        query_failures=query_failures,
        commit_mean_ms=statistics.mean(commit_timings),
        commit_p95_ms=percentile(commit_timings, 0.95),
        baseline_quality=baseline,
        post_insert_quality=post_insert,
        post_delete_quality=post_delete,
        recall_at_10_delta_after_insert=(
            post_insert.recall_at_10 - baseline.recall_at_10
        ),
        recall_at_10_delta_after_delete=(
            post_delete.recall_at_10 - baseline.recall_at_10
        ),
        probe_rows_after_cleanup=probe_rows,
        orphan_chunks_after_cleanup=orphans,
    )

    if write_failures or query_failures:
        raise RuntimeError(
            f"Concurrency failures: writes={write_failures}, queries={query_failures}."
        )
    if probe_rows != 0 or orphans != 0:
        raise RuntimeError("Concurrency cleanup left rows behind.")

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIRECTORY / f"vector_concurrency_{timestamp}.json"
    path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")

    print(f"Writers: {args.writers}")
    print(f"Rows inserted: {result.rows_inserted}")
    print(f"Concurrent semantic queries: {args.queries}")
    print(f"Write failures: {write_failures}")
    print(f"Query failures: {query_failures}")
    print(f"Commit mean: {result.commit_mean_ms:.3f} ms")
    print(f"Commit P95: {result.commit_p95_ms:.3f} ms")
    print(
        "Recall@10 baseline/post-insert/post-delete: "
        f"{baseline.recall_at_10:.3f} / "
        f"{post_insert.recall_at_10:.3f} / "
        f"{post_delete.recall_at_10:.3f}"
    )
    print(f"Orphan chunks after cleanup: {orphans}")
    print(f"Saved results to {path}")

    await database_manager.dispose()


def main() -> None:
    """Run the asynchronous stress experiment."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
