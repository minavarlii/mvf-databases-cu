"""Measure HNSW cache-size interaction on a large scratch vector index."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import database_manager
from experiments.environment import collect_environment
from experiments.vector_scale import (
    SEARCH_SQL,
    drop_probe_if_present,
    measure_multiplier,
    mib,
)

RESULTS_DIRECTORY = Path("experiments/results")
SUMMARY_PATH = Path("docs/vector-cache-sweep-results.md")
DEFAULT_CACHE_MIB = (4, 16, 64)
DEFAULT_MULTIPLIER = 25


@dataclass(frozen=True, slots=True)
class CacheSweepResult:
    """One cache setting measured against a freshly rebuilt scratch index."""

    cache_mib: int
    cache_bytes: int
    rows: int
    index_build_time_ms: float
    query_mean_ms: float
    query_median_ms: float
    query_p95_ms: float
    top5_ids: list[int]


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
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    return parser.parse_args()


def set_global_cache_size(cache_bytes: int) -> int:
    """Set mhnsw_max_cache_size through the local Compose admin connection."""
    root_password = os.environ.get("DB_ROOT_PASSWORD", "")
    if not root_password:
        raise RuntimeError(
            "DB_ROOT_PASSWORD is required for the cache sweep because "
            "mhnsw_max_cache_size is a GLOBAL server variable."
        )

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
        (
            f"SET GLOBAL mhnsw_max_cache_size = {cache_bytes}; "
            "SELECT @@GLOBAL.mhnsw_max_cache_size;"
        ),
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            "MariaDB did not report mhnsw_max_cache_size after SET GLOBAL"
        )
    return int(lines[-1])


async def fetch_top5_ids(session: AsyncSession, embedding: str) -> list[int]:
    """Return the current indexed top-5 ids for stability comparison."""
    result = await session.execute(
        text(SEARCH_SQL),
        {"embedding": embedding},
    )
    return [int(row[0]) for row in result.all()]


def render_markdown(
    *,
    original_cache_bytes: int,
    multiplier: int,
    results: list[CacheSweepResult],
    artifact_name: str,
) -> str:
    """Render the cache-sweep report without copying values into the README."""
    baseline = results[0].top5_ids if results else []
    lines = [
        "# MariaDB `mhnsw_max_cache_size` sweep",
        "",
        (
            "This experiment rebuilds the same large scratch `M=8` cosine vector "
            "index once per cache setting. It changes the MariaDB GLOBAL "
            "`mhnsw_max_cache_size`, measures build/search latency, checks top-5 "
            "stability, then restores the original server value."
        ),
        "",
        f"- Scratch corpus multiplier: **{multiplier}×**",
        f"- Original cache setting: **{mib(original_cache_bytes):.1f} MiB**",
        "",
        "| Cache | Rows | Index build | Mean query | P95 query | Top-5 stable |",
        "|---:|---:|---:|---:|---:|:---:|",
    ]
    for item in results:
        lines.append(
            f"| {item.cache_mib} MiB | {item.rows:,} | "
            f"{item.index_build_time_ms / 1000:.3f} s | "
            f"{item.query_mean_ms:.3f} ms | {item.query_p95_ms:.3f} ms | "
            f"{'yes' if item.top5_ids == baseline else 'no'} |"
        )
    lines.extend(
        [
            "",
            (
                "The cache setting is a server-level limit, not an estimate of "
                "resident index memory. Results therefore report only the configured "
                "limit and observed build/search behavior."
            ),
            "",
            f"Machine-readable artifact: `experiments/results/{artifact_name}`",
            "",
        ]
    )
    return "\n".join(lines)


async def async_main() -> None:
    """Run the cache sweep and restore the original global setting."""
    args = parse_args()
    if args.multiplier < 1 or args.warmups < 0 or args.runs < 1:
        raise ValueError("multiplier/runs must be positive and warmups must be >= 0")
    if not args.cache_mib or any(value < 1 for value in args.cache_mib):
        raise ValueError("cache sizes must be positive MiB values")

    environment = await collect_environment()
    results: list[CacheSweepResult] = []

    async with database_manager.session() as session:
        source_count = await session.scalar(text("SELECT COUNT(*) FROM chunks"))
        source_rows = int(source_count or 0)
        if source_rows == 0:
            raise RuntimeError("chunks is empty; restore or ingest the corpus first")
        embedding = str(
            await session.scalar(
                text("SELECT VEC_ToText(embedding) FROM chunks ORDER BY id LIMIT 1")
            )
        )
        original_cache_bytes = int(
            await session.scalar(text("SELECT @@GLOBAL.mhnsw_max_cache_size")) or 0
        )

        try:
            for cache_mib in args.cache_mib:
                requested_bytes = cache_mib * 1024 * 1024
                applied_bytes = set_global_cache_size(requested_bytes)
                if applied_bytes != requested_bytes:
                    raise RuntimeError(
                        "MariaDB applied a different cache value: "
                        f"requested {requested_bytes}, got {applied_bytes}"
                    )

                scale = await measure_multiplier(
                    session,
                    multiplier=args.multiplier,
                    source_rows=source_rows,
                    embedding=embedding,
                    warmups=args.warmups,
                    runs=args.runs,
                )
                top5_ids = await fetch_top5_ids(session, embedding)
                result = CacheSweepResult(
                    cache_mib=cache_mib,
                    cache_bytes=applied_bytes,
                    rows=scale.rows,
                    index_build_time_ms=scale.index_build_time_ms,
                    query_mean_ms=scale.query_mean_ms,
                    query_median_ms=scale.query_median_ms,
                    query_p95_ms=scale.query_p95_ms,
                    top5_ids=top5_ids,
                )
                results.append(result)
                print(
                    f"cache={cache_mib}MiB: rows={result.rows:,}, "
                    f"build={result.index_build_time_ms / 1000:.3f}s, "
                    f"mean={result.query_mean_ms:.3f}ms, "
                    f"p95={result.query_p95_ms:.3f}ms"
                )
        finally:
            await drop_probe_if_present(session)
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
        "warmups": args.warmups,
        "runs": args.runs,
        "original_mhnsw_max_cache_size_bytes": original_cache_bytes,
        "results": [asdict(item) for item in results],
    }
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(
        render_markdown(
            original_cache_bytes=original_cache_bytes,
            multiplier=args.multiplier,
            results=results,
            artifact_name=artifact_name,
        ),
        encoding="utf-8",
    )
    print(f"Saved results to {artifact_path}")
    print(f"Saved readable summary to {SUMMARY_PATH}")
    await database_manager.dispose()


def main() -> None:
    """Run the cache sweep."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
