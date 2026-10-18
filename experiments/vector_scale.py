"""Measure MariaDB vector-index build and search scaling on scratch copies."""

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
from experiments.environment import EnvironmentMetadata, collect_environment

RESULTS_DIRECTORY = Path("experiments/results")
SUMMARY_PATH = Path("docs/vector-scale-results.md")
DEFAULT_MULTIPLIERS = (1, 5, 10, 25)
VECTOR_DIMENSIONS = 384
FLOAT32_BYTES = 4

CREATE_PROBE_SQL = """
CREATE TABLE vector_scale_probe (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_chunk_id BIGINT UNSIGNED NOT NULL,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB
"""
COPY_CORPUS_SQL = """
INSERT INTO vector_scale_probe (source_chunk_id, embedding)
SELECT id, embedding
FROM chunks
ORDER BY id
"""
CREATE_VECTOR_INDEX_SQL = """
CREATE VECTOR INDEX ix_vector_scale_embedding
ON vector_scale_probe (embedding)
M = 8
DISTANCE = cosine
"""
SEARCH_SQL = """
SELECT id
FROM vector_scale_probe
ORDER BY VEC_DISTANCE_COSINE(
    embedding,
    VEC_FromText(:embedding)
) ASC
LIMIT 5
"""
TABLE_EXISTS_SQL = """
SELECT COUNT(*)
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'vector_scale_probe'
"""


@dataclass(frozen=True, slots=True)
class ScaleResult:
    """One scratch-table scale measurement."""

    multiplier: int
    rows: int
    raw_vector_bytes: int
    load_time_ms: float
    index_build_time_ms: float
    query_mean_ms: float
    query_median_ms: float
    query_p95_ms: float


def parse_args() -> argparse.Namespace:
    """Parse experiment options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--multipliers",
        nargs="+",
        type=int,
        default=list(DEFAULT_MULTIPLIERS),
        help="Corpus-copy multipliers, e.g. 1 5 10 25.",
    )
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile used by the other harnesses."""
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


async def drop_probe_if_present(session: AsyncSession) -> None:
    """Drop the scratch table without emitting a missing-table warning."""
    exists = int(await session.scalar(text(TABLE_EXISTS_SQL)) or 0)
    if exists:
        await session.execute(text("DROP TABLE vector_scale_probe"))
        await session.commit()


async def benchmark_query(
    session: AsyncSession,
    *,
    embedding: str,
    warmups: int,
    runs: int,
) -> tuple[float, float, float]:
    """Measure indexed top-5 search on the scratch table."""
    params = {"embedding": embedding}
    for _ in range(warmups):
        await session.execute(text(SEARCH_SQL), params)

    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        await session.execute(text(SEARCH_SQL), params)
        samples.append((time.perf_counter() - started) * 1000)

    return (
        statistics.mean(samples),
        statistics.median(samples),
        percentile(samples, 0.95),
    )


async def measure_multiplier(
    session: AsyncSession,
    *,
    multiplier: int,
    source_rows: int,
    embedding: str,
    warmups: int,
    runs: int,
) -> ScaleResult:
    """Build and query an isolated repeated-corpus scratch table."""
    await drop_probe_if_present(session)
    await session.execute(text(CREATE_PROBE_SQL))
    await session.commit()

    load_started = time.perf_counter()
    for _ in range(multiplier):
        await session.execute(text(COPY_CORPUS_SQL))
    await session.commit()
    load_time_ms = (time.perf_counter() - load_started) * 1000

    build_started = time.perf_counter()
    await session.execute(text(CREATE_VECTOR_INDEX_SQL))
    await session.commit()
    index_build_time_ms = (time.perf_counter() - build_started) * 1000

    await session.execute(text("ANALYZE TABLE vector_scale_probe"))
    await session.commit()
    query_mean, query_median, query_p95 = await benchmark_query(
        session,
        embedding=embedding,
        warmups=warmups,
        runs=runs,
    )

    rows = source_rows * multiplier
    return ScaleResult(
        multiplier=multiplier,
        rows=rows,
        raw_vector_bytes=rows * VECTOR_DIMENSIONS * FLOAT32_BYTES,
        load_time_ms=load_time_ms,
        index_build_time_ms=index_build_time_ms,
        query_mean_ms=query_mean,
        query_median_ms=query_median,
        query_p95_ms=query_p95,
    )


def mib(value: int) -> float:
    """Convert bytes to MiB."""
    return value / (1024 * 1024)


def render_markdown(
    *,
    environment: EnvironmentMetadata,
    source_rows: int,
    cache_bytes: int,
    results: list[ScaleResult],
    artifact_name: str,
) -> str:
    """Render a checked-in human-readable scale report."""
    lines = [
        "# MariaDB vector-index scale probe",
        "",
        "This scratch-table experiment repeats the canonical 3,940-vector corpus "
        "without changing production tables, then rebuilds the same `M=8` cosine "
        "`VECTOR INDEX`. It measures index build cost and indexed top-5 query latency "
        "while recording the server's configured HNSW cache ceiling.",
        "",
        f"- Source vectors: **{source_rows:,}**",
        (
            "- `mhnsw_max_cache_size`: "
            f"**{mib(cache_bytes):.1f} MiB** ({cache_bytes:,} bytes)"
        ),
        f"- MariaDB: **{environment.mariadb_version}**",
        f"- OS/architecture: **{environment.os} / {environment.architecture}**",
        "",
        (
            "| Corpus multiple | Rows | Raw vector payload | Index build | "
            "Mean query | P95 query |"
        ),
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item.multiplier}× | {item.rows:,} | "
            f"{mib(item.raw_vector_bytes):.1f} MiB | "
            f"{item.index_build_time_ms / 1000:.3f} s | "
            f"{item.query_mean_ms:.3f} ms | {item.query_p95_ms:.3f} ms |"
        )
    lines.extend(
        [
            "",
            "The repeated vectors make this a **server/index scaling probe**, not a "
            "retrieval-quality benchmark. Recall/MRR continue to come from the real "
            "40-question corpus harnesses. The scratch table is dropped after the run.",
            "",
            "MariaDB 11.8 does not expose a reliable per-index resident-memory figure "
            "through the metadata path used by this harness. In particular, ordinary "
            "`information_schema.TABLES.INDEX_LENGTH` is not treated as HNSW memory. "
            "The experiment therefore reports the configured `mhnsw_max_cache_size` "
            "ceiling and raw vector payload, but does not invent a "
            "per-index memory value.",
            "",
            f"Machine-readable artifact: `experiments/results/{artifact_name}`",
            "",
        ]
    )
    return "\n".join(lines)


async def async_main() -> None:
    """Run the vector-index scale experiment."""
    args = parse_args()
    if args.warmups < 0 or args.runs < 1:
        raise ValueError("warmups must be >= 0 and runs must be >= 1")
    if not args.multipliers or any(value < 1 for value in args.multipliers):
        raise ValueError("all multipliers must be positive integers")

    environment = await collect_environment()
    results: list[ScaleResult] = []

    async with database_manager.session() as session:
        source_count = await session.scalar(text("SELECT COUNT(*) FROM chunks"))
        source_rows = int(source_count or 0)
        if source_rows == 0:
            raise RuntimeError("chunks is empty; restore or ingest the corpus first")

        embedding_value = await session.scalar(
            text("SELECT VEC_ToText(embedding) FROM chunks ORDER BY id LIMIT 1")
        )
        embedding = str(embedding_value)
        cache_bytes = int(
            await session.scalar(text("SELECT @@GLOBAL.mhnsw_max_cache_size")) or 0
        )

        try:
            for multiplier in args.multipliers:
                result = await measure_multiplier(
                    session,
                    multiplier=multiplier,
                    source_rows=source_rows,
                    embedding=embedding,
                    warmups=args.warmups,
                    runs=args.runs,
                )
                results.append(result)
                print(
                    f"{multiplier}x: rows={result.rows:,}, "
                    f"build={result.index_build_time_ms / 1000:.3f}s, "
                    f"mean={result.query_mean_ms:.3f}ms, "
                    f"p95={result.query_p95_ms:.3f}ms"
                )
        finally:
            await drop_probe_if_present(session)

    executed_at = datetime.now(UTC)
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    artifact_name = f"vector_scale_{executed_at:%Y%m%dT%H%M%SZ}.json"
    artifact_path = RESULTS_DIRECTORY / artifact_name
    payload = {
        "executed_at": executed_at.isoformat(),
        "environment": asdict(environment),
        "source_rows": source_rows,
        "dimensions": VECTOR_DIMENSIONS,
        "mhnsw_max_cache_size_bytes": cache_bytes,
        "memory_measurement_note": (
            "No per-index HNSW resident-memory value is reported: "
            "information_schema.TABLES.INDEX_LENGTH is not treated as HNSW memory."
        ),
        "warmups": args.warmups,
        "runs": args.runs,
        "results": [asdict(item) for item in results],
    }
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    SUMMARY_PATH.write_text(
        render_markdown(
            environment=environment,
            source_rows=source_rows,
            cache_bytes=cache_bytes,
            results=results,
            artifact_name=artifact_name,
        ),
        encoding="utf-8",
    )
    print(f"Saved results to {artifact_path}")
    print(f"Saved readable summary to {SUMMARY_PATH}")
    await database_manager.dispose()


def main() -> None:
    """Run the experiment."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
