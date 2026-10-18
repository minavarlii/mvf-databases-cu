"""Measure HNSW cache-size interaction with repeated large-index rebuilds."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import database_manager
from backend.app.services import EmbeddingService
from experiments.environment import collect_environment
from experiments.recall import GROUND_TRUTH_PATH, load_ground_truth
from experiments.vector_scale import (
    CREATE_VECTOR_INDEX_SQL,
    SEARCH_SQL,
    mib,
    percentile,
)

RESULTS_DIRECTORY = Path("experiments/results")
SUMMARY_PATH = Path("docs/vector-cache-sweep-results.md")
DEFAULT_GENERATED_SUMMARY_PATH = Path(
    "experiments/results/vector-cache-sweep-latest.md"
)
DEFAULT_CACHE_MIB = (4, 16, 64)
DEFAULT_MULTIPLIER = 25
DEFAULT_REBUILDS = 3
DEFAULT_QUERY_COUNT = 20
VECTOR_DIMENSIONS = 384
PERTURBATION_RADIANS = 0.0005
INSERT_BATCH_SIZE = 200
CACHE_SET_SQL = {
    1 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 1048576; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    2 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 2097152; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    4 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 4194304; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    8 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 8388608; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    16 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 16777216; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    32 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 33554432; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    64 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 67108864; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    128 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 134217728; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    256 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 268435456; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
    512 * 1024 * 1024: (
        "SET GLOBAL mhnsw_max_cache_size = 536870912; "
        "SELECT @@GLOBAL.mhnsw_max_cache_size;"
    ),
}

CREATE_PROBE_SQL = """
CREATE TABLE vector_scale_probe (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_chunk_id BIGINT UNSIGNED NOT NULL,
    copy_number INT UNSIGNED NOT NULL,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_vector_scale_source_copy (source_chunk_id, copy_number)
) ENGINE=InnoDB
"""
INSERT_PROBE_SQL = """
INSERT INTO vector_scale_probe (
    source_chunk_id,
    copy_number,
    embedding
)
VALUES (
    :source_chunk_id,
    :copy_number,
    VEC_FromText(:embedding)
)
"""
SOURCE_EMBEDDINGS_SQL = """
SELECT id, VEC_ToText(embedding)
FROM chunks
ORDER BY id
"""
INDEX_EXISTS_SQL = """
SELECT COUNT(*)
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'vector_scale_probe'
  AND INDEX_NAME = 'ix_vector_scale_embedding'
"""
DROP_VECTOR_INDEX_SQL = """
DROP INDEX ix_vector_scale_embedding
ON vector_scale_probe
"""
DROP_PROBE_SQL = "DROP TABLE IF EXISTS vector_scale_probe"
ANALYZE_PROBE_SQL = "ANALYZE TABLE vector_scale_probe"


@dataclass(frozen=True, slots=True)
class QueryMeasurement:
    """One measured ground-truth query against one rebuilt index."""

    question_id: str
    mean_ms: float
    median_ms: float
    p95_ms: float
    samples_ms: tuple[float, ...]
    top5_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RebuildMeasurement:
    """One complete index rebuild and multi-query measurement."""

    rebuild_number: int
    index_build_time_ms: float
    query_mean_ms: float
    query_median_ms: float
    query_p95_ms: float
    overlap_with_first_rebuild_in_setting: float
    queries: tuple[QueryMeasurement, ...]


@dataclass(frozen=True, slots=True)
class CacheSweepResult:
    """Aggregate measurements for one cache setting."""

    cache_mib: int
    cache_bytes: int
    rows: int
    rebuilds: tuple[RebuildMeasurement, ...]
    build_mean_ms: float
    build_stddev_ms: float
    build_min_ms: float
    build_max_ms: float
    query_mean_ms: float
    query_median_ms: float
    query_p95_ms: float
    within_setting_pairwise_top5_overlap: float


def parse_args() -> argparse.Namespace:
    """Parse cache-sweep options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-mib",
        nargs="+",
        type=int,
        default=list(DEFAULT_CACHE_MIB),
        help="Global mhnsw_max_cache_size values in MiB.",
    )
    parser.add_argument("--multiplier", type=int, default=DEFAULT_MULTIPLIER)
    parser.add_argument("--rebuilds", type=int, default=DEFAULT_REBUILDS)
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERY_COUNT)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=5)
    return parser.parse_args()


def set_global_cache_size(cache_bytes: int) -> int:
    """Set mhnsw_max_cache_size through the local Compose admin connection."""
    root_password = os.environ.get("DB_ROOT_PASSWORD", "")
    if not root_password:
        raise RuntimeError(
            "DB_ROOT_PASSWORD is required for the cache sweep because "
            "mhnsw_max_cache_size is a GLOBAL server variable."
        )

    sql = CACHE_SET_SQL.get(cache_bytes)
    if sql is None:
        supported = ", ".join(
            str(value // (1024 * 1024)) for value in sorted(CACHE_SET_SQL)
        )
        raise ValueError(
            "Unsupported cache size for the static SQL allowlist: "
            f"{cache_bytes} bytes. Supported MiB values: {supported}."
        )

    admin_host = os.environ.get("MVF_CACHE_ADMIN_HOST", "").strip()
    if admin_host:
        command = [
            "mariadb",
            "-h",
            admin_host,
            "-P",
            os.environ.get("DB_PORT", "3306"),
            "-uroot",
            "-N",
            "-e",
            sql,
        ]
        process_env = os.environ.copy()
        process_env["MYSQL_PWD"] = root_password
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            f"MYSQL_PWD={root_password}",
            "mariadb",
            "mariadb",
            "-uroot",
            "-N",
            "-e",
            sql,
        ]
        process_env = None

    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=process_env,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            "MariaDB did not report mhnsw_max_cache_size after SET GLOBAL"
        )
    return int(lines[-1])


def perturb_embedding(
    embedding: list[float],
    *,
    source_chunk_id: int,
    copy_number: int,
) -> list[float]:
    """Create a deterministic distinct copy while preserving L2 norm.

    A tiny 2-D rotation changes two coordinates. Rotation preserves vector norm,
    avoids exact duplicate vectors, and is deterministic for reproducible rebuilds.
    """
    if copy_number == 0:
        return embedding

    pivot = max(range(len(embedding)), key=lambda index: abs(embedding[index]))
    second = (pivot + 1 + (source_chunk_id + copy_number * 31) % 383) % 384
    if second == pivot:
        second = (second + 1) % 384

    angle = PERTURBATION_RADIANS * copy_number
    cosine = math.cos(angle)
    sine = math.sin(angle)
    first_value = embedding[pivot]
    second_value = embedding[second]

    result = embedding.copy()
    result[pivot] = first_value * cosine - second_value * sine
    result[second] = first_value * sine + second_value * cosine
    return result


async def drop_index_if_present(session: AsyncSession) -> None:
    """Drop the scratch vector index if it exists."""
    exists = int(await session.scalar(text(INDEX_EXISTS_SQL)) or 0)
    if exists:
        await session.execute(text(DROP_VECTOR_INDEX_SQL))
        await session.commit()


def parse_vector_text(raw_value: object) -> list[float]:
    """Parse VEC_ToText output into a typed floating-point vector."""
    payload = json.loads(str(raw_value))
    if not isinstance(payload, list):
        raise ValueError("VEC_ToText did not return a JSON array")
    return [float(value) for value in payload]


async def prepare_distinct_probe(
    session: AsyncSession,
    *,
    multiplier: int,
) -> tuple[int, int]:
    """Load a deterministic 25x-style scratch corpus with distinct vectors."""
    await session.execute(text(DROP_PROBE_SQL))
    await session.commit()
    await session.execute(text(CREATE_PROBE_SQL))
    await session.commit()

    source_result = await session.execute(text(SOURCE_EMBEDDINGS_SQL))
    source_rows = [
        (int(row[0]), parse_vector_text(row[1])) for row in source_result.all()
    ]
    if not source_rows:
        raise RuntimeError("chunks is empty; restore or ingest the corpus first")

    expected_dimensions = {len(values) for _, values in source_rows}
    if expected_dimensions != {VECTOR_DIMENSIONS}:
        raise RuntimeError(
            f"Unexpected source embedding dimensions: {sorted(expected_dimensions)}"
        )

    batch: list[dict[str, int | str]] = []
    inserted = 0
    for copy_number in range(multiplier):
        for source_chunk_id, source_embedding in source_rows:
            vector = perturb_embedding(
                source_embedding,
                source_chunk_id=source_chunk_id,
                copy_number=copy_number,
            )
            batch.append(
                {
                    "source_chunk_id": source_chunk_id,
                    "copy_number": copy_number,
                    "embedding": json.dumps(vector, separators=(",", ":")),
                }
            )
            if len(batch) >= INSERT_BATCH_SIZE:
                await session.execute(text(INSERT_PROBE_SQL), batch)
                inserted += len(batch)
                batch.clear()

        print(
            f"loaded distinct copy {copy_number + 1}/{multiplier} "
            f"({inserted + len(batch):,} rows prepared)"
        )

    if batch:
        await session.execute(text(INSERT_PROBE_SQL), batch)
        inserted += len(batch)
    await session.commit()

    expected_rows = len(source_rows) * multiplier
    if inserted != expected_rows:
        raise RuntimeError(
            f"Scratch corpus row mismatch: expected {expected_rows}, "
            f"inserted {inserted}"
        )

    actual_rows = int(
        await session.scalar(text("SELECT COUNT(*) FROM vector_scale_probe")) or 0
    )
    if actual_rows != expected_rows:
        raise RuntimeError(
            f"Scratch corpus count mismatch: expected {expected_rows}, "
            f"got {actual_rows}"
        )

    return len(source_rows), actual_rows


async def prepare_query_embeddings(query_count: int) -> list[tuple[str, str]]:
    """Embed real ground-truth questions outside database timing."""
    questions = load_ground_truth(GROUND_TRUTH_PATH)[:query_count]
    if len(questions) < query_count:
        raise ValueError(
            f"Requested {query_count} queries, but ground truth has {len(questions)}"
        )

    embedding_service = EmbeddingService()
    embeddings = await embedding_service.embed_many(
        [question.question for question in questions]
    )
    return [
        (
            question.question_id,
            json.dumps(embedding, separators=(",", ":")),
        )
        for question, embedding in zip(questions, embeddings, strict=True)
    ]


async def measure_query(
    session: AsyncSession,
    *,
    question_id: str,
    embedding: str,
    warmups: int,
    runs: int,
) -> QueryMeasurement:
    """Measure one real query repeatedly and capture its current top-5."""
    params = {"embedding": embedding}
    for _ in range(warmups):
        await session.execute(text(SEARCH_SQL), params)

    samples: list[float] = []
    top5_ids: tuple[int, ...] = ()
    for _ in range(runs):
        started = time.perf_counter()
        result = await session.execute(text(SEARCH_SQL), params)
        samples.append((time.perf_counter() - started) * 1000)
        top5_ids = tuple(int(row[0]) for row in result.all())

    return QueryMeasurement(
        question_id=question_id,
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        p95_ms=percentile(samples, 0.95),
        samples_ms=tuple(samples),
        top5_ids=top5_ids,
    )


def mean_top5_overlap_between_rebuilds(
    left: tuple[QueryMeasurement, ...],
    right: tuple[QueryMeasurement, ...],
) -> float:
    """Return mean top-5 set overlap across matching query ids."""
    right_by_id = {item.question_id: set(item.top5_ids) for item in right}
    overlaps: list[float] = []
    for measurement in left:
        expected = right_by_id[measurement.question_id]
        observed = set(measurement.top5_ids)
        overlaps.append(len(expected & observed) / 5)
    return statistics.mean(overlaps)


def mean_pairwise_overlap_within_setting(
    rebuilds: list[RebuildMeasurement],
) -> float:
    """Average every distinct rebuild pair; never compare a rebuild to itself."""
    overlaps: list[float] = []
    for left_index, left in enumerate(rebuilds):
        for right in rebuilds[left_index + 1 :]:
            overlaps.append(
                mean_top5_overlap_between_rebuilds(left.queries, right.queries)
            )
    if not overlaps:
        raise ValueError("At least two rebuilds are required for pairwise overlap")
    return statistics.mean(overlaps)


def cross_setting_first_rebuild_overlaps(
    results: list[CacheSweepResult],
) -> list[tuple[int, float | None]]:
    """Compare first rebuilds across settings.

    Keep this separate from within-setting rebuild variance.
    """
    if not results:
        return []
    baseline = results[0].rebuilds[0].queries
    comparisons: list[tuple[int, float | None]] = []
    for index, result in enumerate(results):
        if index == 0:
            comparisons.append((result.cache_mib, None))
            continue
        comparisons.append(
            (
                result.cache_mib,
                mean_top5_overlap_between_rebuilds(
                    baseline, result.rebuilds[0].queries
                ),
            )
        )
    return comparisons


async def measure_rebuild(
    session: AsyncSession,
    *,
    rebuild_number: int,
    queries: list[tuple[str, str]],
    warmups: int,
    runs: int,
    setting_reference: dict[str, set[int]],
) -> RebuildMeasurement:
    """Build one fresh HNSW index and measure all prepared queries."""
    await drop_index_if_present(session)

    started = time.perf_counter()
    await session.execute(text(CREATE_VECTOR_INDEX_SQL))
    await session.commit()
    build_time_ms = (time.perf_counter() - started) * 1000

    await session.execute(text(ANALYZE_PROBE_SQL))
    await session.commit()

    query_results = tuple(
        [
            await measure_query(
                session,
                question_id=question_id,
                embedding=embedding,
                warmups=warmups,
                runs=runs,
            )
            for question_id, embedding in queries
        ]
    )
    all_query_samples = [sample for item in query_results for sample in item.samples_ms]

    if not setting_reference:
        setting_reference.update(
            {item.question_id: set(item.top5_ids) for item in query_results}
        )

    return RebuildMeasurement(
        rebuild_number=rebuild_number,
        index_build_time_ms=build_time_ms,
        query_mean_ms=statistics.mean(all_query_samples),
        query_median_ms=statistics.median(all_query_samples),
        query_p95_ms=percentile(all_query_samples, 0.95),
        overlap_with_first_rebuild_in_setting=(
            1.0
            if rebuild_number == 1
            else statistics.mean(
                len(setting_reference[item.question_id] & set(item.top5_ids)) / 5
                for item in query_results
            )
        ),
        queries=query_results,
    )


def summarize_cache_setting(
    *,
    cache_mib: int,
    cache_bytes: int,
    rows: int,
    rebuilds: list[RebuildMeasurement],
) -> CacheSweepResult:
    """Aggregate repeated rebuilds for one cache size."""
    build_times = [item.index_build_time_ms for item in rebuilds]
    all_query_samples = [
        sample
        for rebuild in rebuilds
        for query in rebuild.queries
        for sample in query.samples_ms
    ]
    return CacheSweepResult(
        cache_mib=cache_mib,
        cache_bytes=cache_bytes,
        rows=rows,
        rebuilds=tuple(rebuilds),
        build_mean_ms=statistics.mean(build_times),
        build_stddev_ms=(
            statistics.stdev(build_times) if len(build_times) > 1 else 0.0
        ),
        build_min_ms=min(build_times),
        build_max_ms=max(build_times),
        query_mean_ms=statistics.mean(all_query_samples),
        query_median_ms=statistics.median(all_query_samples),
        query_p95_ms=percentile(all_query_samples, 0.95),
        within_setting_pairwise_top5_overlap=(
            mean_pairwise_overlap_within_setting(rebuilds)
        ),
    )


def render_markdown(
    *,
    original_cache_bytes: int,
    multiplier: int,
    source_rows: int,
    query_count: int,
    rebuild_count: int,
    results: list[CacheSweepResult],
    artifact_name: str,
) -> str:
    """Render a human-readable repeated cache-sweep report."""
    lines = [
        "# MariaDB `mhnsw_max_cache_size` repeated-build sweep",
        "",
        (
            "This experiment uses a deterministic perturbed scratch corpus: each "
            "copy is a tiny norm-preserving rotation of a real stored vector, so the "
            "98,500-row workload does not contain exact duplicated vectors."
        ),
        "",
        f"- Source vectors: **{source_rows:,}**",
        f"- Scratch corpus multiplier: **{multiplier}×**",
        f"- Ground-truth query vectors: **{query_count}**",
        f"- Independent index rebuilds per cache setting: **{rebuild_count}**",
        f"- Original cache setting: **{mib(original_cache_bytes):.1f} MiB**",
        "",
        (
            "| Cache | Rows | Build mean | Build stddev | Build min–max | "
            "Query mean | Query P95 | Within-setting pairwise top-5 overlap |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item.cache_mib} MiB | {item.rows:,} | "
            f"{item.build_mean_ms / 1000:.3f} s | "
            f"{item.build_stddev_ms / 1000:.3f} s | "
            f"{item.build_min_ms / 1000:.3f}–{item.build_max_ms / 1000:.3f} s | "
            f"{item.query_mean_ms:.3f} ms | {item.query_p95_ms:.3f} ms | "
            f"{item.within_setting_pairwise_top5_overlap * 100:.1f}% |"
        )

    if results:
        fastest = min(results, key=lambda item: item.build_mean_ms)
        slowest = max(results, key=lambda item: item.build_mean_ms)
        build_ratio = slowest.build_mean_ms / fastest.build_mean_ms
        query_values = [item.query_mean_ms for item in results]
        query_spread = max(query_values) - min(query_values)
        minimum_overlap = min(
            item.within_setting_pairwise_top5_overlap for item in results
        )
        interpretation = (
            f"Across repeated rebuilds, the fastest mean build occurred at "
            f"{fastest.cache_mib} MiB and the slowest at {slowest.cache_mib} MiB "
            f"({build_ratio:.2f}× apart). Mean query latency varied by only "
            f"{query_spread:.3f} ms across cache settings. The minimum "
            f"within-setting pairwise top-5 overlap was {minimum_overlap * 100:.1f}%. "
            "Because exact duplicate vectors were removed, any remaining ordering "
            "differences are treated as ANN rebuild variability rather than duplicate "
            "ties; this experiment does not claim that cache size deterministically "
            "changes retrieval quality."
        )
        lines.extend(["", "## Interpretation", "", interpretation])

        comparisons = cross_setting_first_rebuild_overlaps(results)
        baseline_cache = comparisons[0][0]
        lines.extend(
            [
                "",
                "## Across-cache first-rebuild comparison",
                "",
                (
                    "This table is intentionally separate from the within-setting "
                    "pairwise metric above. It compares only the first rebuild from "
                    f"each setting against the {baseline_cache} MiB first rebuild."
                ),
                "",
                "| Cache | First rebuild top-5 overlap vs baseline |",
                "|---:|---:|",
            ]
        )
        for cache_mib, overlap in comparisons:
            value = "reference" if overlap is None else f"{overlap * 100:.1f}%"
            lines.append(f"| {cache_mib} MiB | {value} |")
        lines.extend(
            [
                "",
                (
                    "Across-cache overlap is descriptive only: changing cache size "
                    "also requires a fresh ANN rebuild, so it is not interpreted "
                    "as a causal retrieval-quality effect of the cache setting."
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "The cache setting is a server-level limit, not an estimate of "
                "resident index memory. Build conclusions use repeated rebuilds and "
                "their variance rather than one build per setting."
            ),
            "",
            f"Machine-readable artifact: `experiments/results/{artifact_name}`",
            "",
        ]
    )
    return "\n".join(lines)


async def async_main() -> None:
    """Run the repeated cache sweep and restore the original server setting."""
    args = parse_args()
    if args.multiplier < 1 or args.rebuilds < 2 or args.queries < 2:
        raise ValueError("multiplier must be positive; rebuilds/queries must be >= 2")
    if args.warmups < 0 or args.runs < 1:
        raise ValueError("warmups must be >= 0 and runs must be >= 1")
    if not args.cache_mib or any(value < 1 for value in args.cache_mib):
        raise ValueError("cache sizes must be positive MiB values")

    environment = await collect_environment()
    queries = await prepare_query_embeddings(args.queries)
    results: list[CacheSweepResult] = []
    async with database_manager.session() as session:
        original_cache_bytes = int(
            await session.scalar(text("SELECT @@GLOBAL.mhnsw_max_cache_size")) or 0
        )

        try:
            source_rows, scratch_rows = await prepare_distinct_probe(
                session,
                multiplier=args.multiplier,
            )
            print(
                f"Prepared {scratch_rows:,} deterministic distinct scratch vectors "
                f"from {source_rows:,} source vectors."
            )

            for cache_mib in args.cache_mib:
                setting_reference_rankings: dict[str, set[int]] = {}
                requested_bytes = cache_mib * 1024 * 1024
                applied_bytes = set_global_cache_size(requested_bytes)
                if applied_bytes != requested_bytes:
                    raise RuntimeError(
                        "MariaDB applied a different cache value: "
                        f"requested {requested_bytes}, got {applied_bytes}"
                    )

                rebuilds: list[RebuildMeasurement] = []
                for rebuild_number in range(1, args.rebuilds + 1):
                    rebuild = await measure_rebuild(
                        session,
                        rebuild_number=rebuild_number,
                        queries=queries,
                        warmups=args.warmups,
                        runs=args.runs,
                        setting_reference=setting_reference_rankings,
                    )
                    rebuilds.append(rebuild)
                    print(
                        f"cache={cache_mib}MiB rebuild={rebuild_number}/"
                        f"{args.rebuilds}: build="
                        f"{rebuild.index_build_time_ms / 1000:.3f}s, "
                        f"query_mean={rebuild.query_mean_ms:.3f}ms, "
                        f"overlap_vs_first_in_setting="
                        f"{rebuild.overlap_with_first_rebuild_in_setting * 100:.1f}%"
                    )

                summary = summarize_cache_setting(
                    cache_mib=cache_mib,
                    cache_bytes=applied_bytes,
                    rows=scratch_rows,
                    rebuilds=rebuilds,
                )
                results.append(summary)
                print(
                    f"cache={cache_mib}MiB summary: build="
                    f"{summary.build_mean_ms / 1000:.3f}s ± "
                    f"{summary.build_stddev_ms / 1000:.3f}s, "
                    f"query_mean={summary.query_mean_ms:.3f}ms, "
                    f"p95={summary.query_p95_ms:.3f}ms"
                )
        finally:
            await session.execute(text(DROP_PROBE_SQL))
            await session.commit()
            if original_cache_bytes > 0:
                set_global_cache_size(original_cache_bytes)

    executed_at = datetime.now(UTC)
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    artifact_name = f"vector_cache_sweep_{executed_at:%Y%m%dT%H%M%SZ}.json"
    artifact_path = RESULTS_DIRECTORY / artifact_name
    payload = {
        "executed_at": executed_at.isoformat(),
        "environment": asdict(environment),
        "multiplier": args.multiplier,
        "source_rows": source_rows,
        "scratch_rows": scratch_rows,
        "distinct_vector_method": (
            "tiny deterministic 2-D rotations of source vectors; L2 norm preserved"
        ),
        "perturbation_radians_per_copy": PERTURBATION_RADIANS,
        "ground_truth_queries": args.queries,
        "rebuilds_per_cache_setting": args.rebuilds,
        "warmups_per_query": args.warmups,
        "runs_per_query": args.runs,
        "original_mhnsw_max_cache_size_bytes": original_cache_bytes,
        "results": [asdict(item) for item in results],
    }
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary_path = Path(
        os.environ.get(
            "MVF_CACHE_SUMMARY_PATH",
            (
                "experiments/results/ubuntu/vector-cache-sweep-results.md"
                if os.environ.get("GITHUB_ACTIONS") == "true"
                else str(DEFAULT_GENERATED_SUMMARY_PATH)
            ),
        )
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        render_markdown(
            original_cache_bytes=original_cache_bytes,
            multiplier=args.multiplier,
            source_rows=source_rows,
            query_count=args.queries,
            rebuild_count=args.rebuilds,
            results=results,
            artifact_name=artifact_name,
        ),
        encoding="utf-8",
    )
    print(f"Saved results to {artifact_path}")
    print(f"Saved readable summary to {summary_path}")
    await database_manager.dispose()


def main() -> None:
    """Run the cache sweep."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
