"""Benchmark MariaDB VECTOR INDEX across multiple M values."""

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
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import database_manager
from backend.app.services import EmbeddingService
from experiments.environment import collect_environment

INDEX_NAME = "ix_chunks_embedding"

DEFAULT_M_VALUES = (4, 8, 16, 32)
PRODUCTION_M = 8

QUERY = "neural network training"
LIMIT = 5

WARMUP_RUNS = 5
MEASURED_RUNS = 50

RESULTS_DIRECTORY = Path("experiments/results")


SEARCH_SQL = """
SELECT
    id AS chunk_id,
    article_id,
    VEC_DISTANCE_COSINE(
        embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM chunks
ORDER BY distance ASC
LIMIT :limit
"""


EXACT_SEARCH_SQL = """
SELECT
    id AS chunk_id,
    article_id,
    VEC_DISTANCE_COSINE(
        embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM chunks IGNORE INDEX (ix_chunks_embedding)
ORDER BY distance ASC
LIMIT :limit
"""


DROP_INDEX_SQL = """
DROP INDEX IF EXISTS ix_chunks_embedding
ON chunks
"""

CREATE_INDEX_SQL_BY_M = {
    4: """
CREATE VECTOR INDEX ix_chunks_embedding
ON chunks (embedding)
M = 4
DISTANCE = cosine
""",
    8: """
CREATE VECTOR INDEX ix_chunks_embedding
ON chunks (embedding)
M = 8
DISTANCE = cosine
""",
    16: """
CREATE VECTOR INDEX ix_chunks_embedding
ON chunks (embedding)
M = 16
DISTANCE = cosine
""",
    32: """
CREATE VECTOR INDEX ix_chunks_embedding
ON chunks (embedding)
M = 32
DISTANCE = cosine
""",
}


def create_index_sql(
    m_value: int,
) -> str:
    """Return static CREATE VECTOR INDEX SQL for a supported M value."""
    try:
        return CREATE_INDEX_SQL_BY_M[m_value]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported vector-index M value: {m_value}. "
            "Supported values are 4, 8, 16, and 32."
        ) from exc


@dataclass(frozen=True, slots=True)
class LatencySummary:
    """Store latency statistics."""

    mean_ms: float
    median_ms: float
    p95_ms: float
    minimum_ms: float
    maximum_ms: float


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Store one M-value experiment result."""

    m: int
    build_time_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    minimum_ms: float
    maximum_ms: float
    exact_overlap_at_k: float
    indexed_chunk_ids: list[int]
    exact_chunk_ids: list[int]


def percentile(
    values: list[float],
    fraction: float,
) -> float:
    """Return nearest-rank percentile."""
    ordered = sorted(values)

    index = round((len(ordered) - 1) * fraction)

    return ordered[index]


def serialize_embedding(
    embedding: list[float],
) -> str:
    """Serialize embedding for VEC_FromText."""
    return json.dumps(
        embedding,
        separators=(",", ":"),
    )


async def execute_search(
    session: AsyncSession,
    *,
    sql: str,
    embedding_json: str,
) -> list[RowMapping]:
    """Run one vector-search query."""
    result = await session.execute(
        text(sql),
        {
            "embedding": embedding_json,
            "limit": LIMIT,
        },
    )

    return list(result.mappings())


async def benchmark_search(
    session: AsyncSession,
    *,
    embedding_json: str,
) -> LatencySummary:
    """Benchmark indexed vector search."""
    for _ in range(WARMUP_RUNS):
        await execute_search(
            session,
            sql=SEARCH_SQL,
            embedding_json=embedding_json,
        )

    samples: list[float] = []

    for _ in range(MEASURED_RUNS):
        started = time.perf_counter()

        await execute_search(
            session,
            sql=SEARCH_SQL,
            embedding_json=embedding_json,
        )

        samples.append((time.perf_counter() - started) * 1000)

    return LatencySummary(
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        p95_ms=percentile(
            samples,
            0.95,
        ),
        minimum_ms=min(samples),
        maximum_ms=max(samples),
    )


async def rebuild_index(
    session: AsyncSession,
    *,
    m_value: int,
) -> float:
    """Drop and rebuild the vector index."""
    await session.execute(text(DROP_INDEX_SQL))

    started = time.perf_counter()

    await session.execute(text(create_index_sql(m_value)))

    build_time_ms = (time.perf_counter() - started) * 1000

    await session.execute(
        text(
            """
            ANALYZE TABLE chunks
            """
        )
    )

    return build_time_ms


def extract_chunk_ids(
    rows: list[RowMapping],
) -> list[int]:
    """Extract chunk IDs from result rows."""
    return [int(row["chunk_id"]) for row in rows]


def overlap_at_k(
    indexed_ids: list[int],
    exact_ids: list[int],
) -> float:
    """Calculate overlap between indexed and exact top-k."""
    indexed = set(indexed_ids)
    exact = set(exact_ids)

    return len(indexed & exact) / len(exact)


async def evaluate_m(
    session: AsyncSession,
    *,
    m_value: int,
    embedding_json: str,
) -> SweepResult:
    """Evaluate one vector-index M value."""
    print()
    print("=" * 72)
    print(f"M = {m_value}")
    print("=" * 72)

    print("Rebuilding vector index...")

    build_time_ms = await rebuild_index(
        session,
        m_value=m_value,
    )

    print(f"Build time: {build_time_ms:.3f} ms")

    exact_rows = await execute_search(
        session,
        sql=EXACT_SEARCH_SQL,
        embedding_json=embedding_json,
    )

    indexed_rows = await execute_search(
        session,
        sql=SEARCH_SQL,
        embedding_json=embedding_json,
    )

    exact_ids = extract_chunk_ids(exact_rows)

    indexed_ids = extract_chunk_ids(indexed_rows)

    overlap = overlap_at_k(
        indexed_ids,
        exact_ids,
    )

    latency = await benchmark_search(
        session,
        embedding_json=embedding_json,
    )

    print(f"Mean:    {latency.mean_ms:.3f} ms")
    print(f"Median:  {latency.median_ms:.3f} ms")
    print(f"P95:     {latency.p95_ms:.3f} ms")
    print(f"Overlap: {overlap * 100:.1f}%")

    return SweepResult(
        m=m_value,
        build_time_ms=build_time_ms,
        mean_ms=latency.mean_ms,
        median_ms=latency.median_ms,
        p95_ms=latency.p95_ms,
        minimum_ms=latency.minimum_ms,
        maximum_ms=latency.maximum_ms,
        exact_overlap_at_k=overlap,
        indexed_chunk_ids=indexed_ids,
        exact_chunk_ids=exact_ids,
    )


async def run(
    *,
    m_values: tuple[int, ...],
) -> None:
    """Run the complete M sweep."""
    embedding_service = EmbeddingService()

    print("Generating benchmark query embedding...")

    embedding = await embedding_service.embed_text(QUERY)

    embedding_json = serialize_embedding(embedding)
    environment = await collect_environment()

    results: list[SweepResult] = []

    try:
        async with database_manager.session() as session:
            for m_value in m_values:
                result = await evaluate_m(
                    session,
                    m_value=m_value,
                    embedding_json=(embedding_json),
                )

                results.append(result)

            print()
            print(f"Restoring production M = {PRODUCTION_M}...")

            await rebuild_index(
                session,
                m_value=PRODUCTION_M,
            )

    finally:
        try:
            async with database_manager.session() as session:
                await rebuild_index(
                    session,
                    m_value=(PRODUCTION_M),
                )

        finally:
            await database_manager.dispose()

    RESULTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = RESULTS_DIRECTORY / (f"vector_index_m_sweep_{timestamp}.json")

    payload = {
        "environment": asdict(environment),
        "mariadb_vector_index": {
            "index_name": INDEX_NAME,
            "distance": "cosine",
            "production_m": (PRODUCTION_M),
        },
        "benchmark": {
            "query": QUERY,
            "limit": LIMIT,
            "warmup_runs": (WARMUP_RUNS),
            "measured_runs": (MEASURED_RUNS),
        },
        "results": [asdict(result) for result in results],
    }

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("Summary")
    print("-" * 72)

    for result in results:
        print(
            f"M={result.m:<3} "
            f"build="
            f"{result.build_time_ms:>9.3f} ms  "
            f"mean="
            f"{result.mean_ms:>7.3f} ms  "
            f"p95="
            f"{result.p95_ms:>7.3f} ms  "
            f"overlap="
            f"{result.exact_overlap_at_k * 100:>5.1f}%"
        )

    print()
    print(f"Saved result to {output_path}")

    print(f"Production index restored to M={PRODUCTION_M}.")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Benchmark MariaDB VECTOR INDEX across M values."),
    )

    parser.add_argument(
        "--m-values",
        type=int,
        nargs="+",
        choices=DEFAULT_M_VALUES,
        default=list(DEFAULT_M_VALUES),
        help=("Vector-index M values to benchmark."),
    )

    return parser.parse_args()


async def main() -> None:
    """Run command."""
    arguments = parse_arguments()

    m_values = tuple(arguments.m_values)

    if not m_values:
        raise ValueError("At least one M value is required.")

    await run(m_values=m_values)


if __name__ == "__main__":
    asyncio.run(main())
