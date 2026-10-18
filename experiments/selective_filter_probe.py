"""Probe highly selective relational predicates against MariaDB ANN search."""

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
from backend.app.db.queries import QueryPlanRow, VectorQueries, VectorSearchResult
from backend.app.services import EmbeddingService
from experiments.environment import EnvironmentMetadata, collect_environment
from experiments.index_vs_bruteforce import set_vector_index_ignored

RESULTS_DIRECTORY = Path("experiments/results")
REPORT_PATH = Path("docs/selective-filter-results.md")

DEFAULT_QUERY = "neural network training"
DEFAULT_LIMIT = 10
DEFAULT_MAX_ELIGIBLE_CHUNKS = 50
DEFAULT_CATEGORY_COUNT = 12
DEFAULT_WARMUPS = 1
DEFAULT_RUNS = 5
DEFAULT_EF_VALUES = (20, 200, 800)
PRODUCTION_EF_SEARCH = 20

SET_EF_SQL_BY_VALUE = {
    20: "SET SESSION mhnsw_ef_search = 20",
    200: "SET SESSION mhnsw_ef_search = 200",
    800: "SET SESSION mhnsw_ef_search = 800",
}

CATEGORY_COUNTS_SQL = """
SELECT
    cat.name AS category,
    COUNT(*) AS eligible_chunks
FROM categories AS cat
INNER JOIN article_categories AS ac
    ON ac.category_id = cat.id
INNER JOIN chunks AS c
    ON c.article_id = ac.article_id
GROUP BY cat.id, cat.name
HAVING COUNT(*) >= :minimum_chunks
   AND COUNT(*) <= :maximum_chunks
ORDER BY eligible_chunks ASC, cat.name ASC
LIMIT :category_count
""".strip()

TOTAL_CHUNKS_SQL = "SELECT COUNT(*) AS total_chunks FROM chunks"


@dataclass(frozen=True, slots=True)
class CandidateCategory:
    """One selective relational predicate chosen from the real corpus."""

    category: str
    eligible_chunks: int
    selectivity: float


@dataclass(frozen=True, slots=True)
class QueryObservation:
    """One indexed or brute-force observation for one category."""

    returned_rows: int
    mean_ms: float
    p95_ms: float
    result_signature: tuple[int, ...]
    execution_plan: tuple[QueryPlanRow, ...]


@dataclass(frozen=True, slots=True)
class EfObservation:
    """Indexed observation at one mhnsw_ef_search setting."""

    ef_search: int
    returned_rows: int
    underfilled: bool
    exact_top_k_overlap: float
    same_top_k: bool
    mean_ms: float
    p95_ms: float
    execution_plan: tuple[QueryPlanRow, ...]


@dataclass(frozen=True, slots=True)
class CategoryResult:
    """Exact and indexed outcomes for one selective category."""

    category: str
    eligible_chunks: int
    selectivity: float
    exact_returned_rows: int
    exact_mean_ms: float
    exact_p95_ms: float
    exact_execution_plan: tuple[QueryPlanRow, ...]
    indexed: tuple[EfObservation, ...]


@dataclass(frozen=True, slots=True)
class SelectiveFilterStudy:
    """Complete selective-filter ANN study."""

    executed_at: str
    environment: EnvironmentMetadata
    query: str
    limit: int
    total_chunks: int
    category_count: int
    minimum_eligible_chunks: int
    maximum_eligible_chunks: int
    warmups: int
    runs: int
    ef_values: tuple[int, ...]
    results: tuple[CategoryResult, ...]
    underfilled_categories_by_ef: dict[str, int]
    mean_exact_top_k_overlap_by_ef: dict[str, float]


def percentile(values: list[float], fraction: float) -> float:
    """Return an interpolated percentile from non-empty values."""
    if not values:
        raise ValueError("Cannot calculate a percentile of no values.")

    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def ef_sql(value: int) -> str:
    """Return a static SET statement for an allowlisted ef_search value."""
    try:
        return SET_EF_SQL_BY_VALUE[value]
    except KeyError as exc:
        supported = ", ".join(str(item) for item in SET_EF_SQL_BY_VALUE)
        raise ValueError(
            f"Unsupported mhnsw_ef_search value {value}; use one of {supported}."
        ) from exc


async def set_ef_search(session: AsyncSession, value: int) -> None:
    """Set MariaDB's session-level HNSW candidate-search parameter."""
    await session.execute(text(ef_sql(value)))


def signature(results: list[VectorSearchResult]) -> tuple[int, ...]:
    """Return the chunk-id signature of ranked search results."""
    return tuple(result.chunk_id for result in results)


def top_k_overlap(indexed: tuple[int, ...], exact: tuple[int, ...]) -> float:
    """Return set overlap relative to the exact result count."""
    if not exact:
        return 1.0 if not indexed else 0.0
    return len(set(indexed) & set(exact)) / len(exact)


async def discover_categories(
    session: AsyncSession,
    *,
    limit: int,
    maximum_chunks: int,
    category_count: int,
) -> tuple[int, list[CandidateCategory]]:
    """Find rare real Wikipedia categories that still contain at least LIMIT chunks."""
    total_result = await session.execute(text(TOTAL_CHUNKS_SQL))
    total_chunks = int(total_result.scalar_one())

    result = await session.execute(
        text(CATEGORY_COUNTS_SQL),
        {
            "minimum_chunks": limit,
            "maximum_chunks": maximum_chunks,
            "category_count": category_count,
        },
    )

    candidates = [
        CandidateCategory(
            category=str(row["category"]),
            eligible_chunks=int(row["eligible_chunks"]),
            selectivity=int(row["eligible_chunks"]) / total_chunks,
        )
        for row in result.mappings()
    ]

    if not candidates:
        raise RuntimeError(
            "No category matched the requested selectivity window; "
            "increase --max-eligible-chunks."
        )

    return total_chunks, candidates


async def measure_category(
    session: AsyncSession,
    *,
    embedding: list[float],
    category: str,
    limit: int,
    warmups: int,
    runs: int,
) -> QueryObservation:
    """Measure one category-filtered query under the session's current settings."""
    queries = VectorQueries(session)

    for _ in range(warmups):
        await queries.hybrid_search(
            embedding=embedding,
            category=category,
            limit=limit,
        )

    latencies: list[float] = []
    results: list[VectorSearchResult] = []
    for _ in range(runs):
        started = time.perf_counter()
        results = await queries.hybrid_search(
            embedding=embedding,
            category=category,
            limit=limit,
        )
        latencies.append((time.perf_counter() - started) * 1000.0)

    plan = await queries.explain_hybrid_search(
        embedding=embedding,
        category=category,
        limit=limit,
    )

    return QueryObservation(
        returned_rows=len(results),
        mean_ms=statistics.mean(latencies),
        p95_ms=percentile(latencies, 0.95),
        result_signature=signature(results),
        execution_plan=tuple(plan),
    )


async def run_indexed(
    *,
    embedding: list[float],
    categories: list[CandidateCategory],
    ef_values: tuple[int, ...],
    limit: int,
    warmups: int,
    runs: int,
) -> dict[tuple[str, int], QueryObservation]:
    """Measure indexed filtered ANN for every category and ef_search value."""
    observations: dict[tuple[str, int], QueryObservation] = {}

    async with database_manager.session() as session:
        for ef_search in ef_values:
            await set_ef_search(session, ef_search)

            for candidate in categories:
                observations[(candidate.category, ef_search)] = await measure_category(
                    session,
                    embedding=embedding,
                    category=candidate.category,
                    limit=limit,
                    warmups=warmups,
                    runs=runs,
                )

        await set_ef_search(session, PRODUCTION_EF_SEARCH)

    return observations


async def run_exact(
    *,
    embedding: list[float],
    categories: list[CandidateCategory],
    limit: int,
    warmups: int,
    runs: int,
) -> dict[str, QueryObservation]:
    """Measure the same filtered queries with the vector index optimizer-ignored."""
    observations: dict[str, QueryObservation] = {}

    async with database_manager.session() as session:
        for candidate in categories:
            observations[candidate.category] = await measure_category(
                session,
                embedding=embedding,
                category=candidate.category,
                limit=limit,
                warmups=warmups,
                runs=runs,
            )

    return observations


def build_results(
    *,
    categories: list[CandidateCategory],
    indexed: dict[tuple[str, int], QueryObservation],
    exact: dict[str, QueryObservation],
    ef_values: tuple[int, ...],
    limit: int,
) -> tuple[CategoryResult, ...]:
    """Combine exact and indexed observations into artifact rows."""
    results: list[CategoryResult] = []

    for candidate in categories:
        exact_observation = exact[candidate.category]
        indexed_rows: list[EfObservation] = []

        for ef_search in ef_values:
            observation = indexed[(candidate.category, ef_search)]
            indexed_rows.append(
                EfObservation(
                    ef_search=ef_search,
                    returned_rows=observation.returned_rows,
                    underfilled=(
                        candidate.eligible_chunks >= limit
                        and observation.returned_rows < limit
                    ),
                    exact_top_k_overlap=top_k_overlap(
                        observation.result_signature,
                        exact_observation.result_signature,
                    ),
                    same_top_k=(
                        observation.result_signature
                        == exact_observation.result_signature
                    ),
                    mean_ms=observation.mean_ms,
                    p95_ms=observation.p95_ms,
                    execution_plan=observation.execution_plan,
                )
            )

        results.append(
            CategoryResult(
                category=candidate.category,
                eligible_chunks=candidate.eligible_chunks,
                selectivity=candidate.selectivity,
                exact_returned_rows=exact_observation.returned_rows,
                exact_mean_ms=exact_observation.mean_ms,
                exact_p95_ms=exact_observation.p95_ms,
                exact_execution_plan=exact_observation.execution_plan,
                indexed=tuple(indexed_rows),
            )
        )

    return tuple(results)


def render_report(study: SelectiveFilterStudy, artifact_path: Path) -> str:
    """Render a concise Markdown report directly from the JSON-backed study object."""
    lines = [
        "# Selective filtered ANN probe",
        "",
        "This report is generated by `make selective-filter`. It deliberately chooses ",
        "real Wikipedia categories containing at least `LIMIT` matching "
        "chunks but only ",
        "a small fraction of the 3,940-vector corpus. That distinguishes ANN/filter ",
        "underfill from the trivial case where fewer than `LIMIT` rows are eligible.",
        "",
        f"- Query: `{study.query}`",
        f"- LIMIT: **{study.limit}**",
        f"- Corpus vectors: **{study.total_chunks:,}**",
        f"- Categories tested: **{study.category_count}**",
        (
            f"- Eligible-chunk window: **{study.minimum_eligible_chunks}–"
            f"{study.maximum_eligible_chunks}**"
        ),
        f"- `mhnsw_ef_search`: **{', '.join(str(v) for v in study.ef_values)}**",
        (
            f"- Repetitions: **{study.runs}** measured after "
            f"**{study.warmups}** warm-up run(s)"
        ),
        "",
        (
            "| Category | Eligible chunks | Selectivity | ef_search | "
            "Returned / LIMIT | Underfilled | Exact top-k overlap | Mean | P95 |"
        ),
        "|---|---:|---:|---:|---:|---|---:|---:|---:|",
    ]

    for result in study.results:
        for observation in result.indexed:
            lines.append(
                "| "
                f"{result.category} | {result.eligible_chunks} | "
                f"{result.selectivity * 100:.3f}% | {observation.ef_search} | "
                f"{observation.returned_rows} / {study.limit} | "
                f"{'**yes**' if observation.underfilled else 'no'} | "
                f"{observation.exact_top_k_overlap * 100:.1f}% | "
                f"{observation.mean_ms:.3f} ms | {observation.p95_ms:.3f} ms |"
            )

    lines.extend(["", "## Finding", ""])

    underfill_parts = [
        f"ef={ef}: {study.underfilled_categories_by_ef[str(ef)]}/{study.category_count}"
        for ef in study.ef_values
    ]
    overlap_parts = [
        f"ef={ef}: {study.mean_exact_top_k_overlap_by_ef[str(ef)] * 100:.1f}%"
        for ef in study.ef_values
    ]

    any_underfill = any(study.underfilled_categories_by_ef.values())
    if any_underfill:
        finding = (
            "The probe reproduced filtered-ANN underfill for at least one highly "
            "selective predicate even though every selected category had at "
            "least LIMIT "
            "eligible chunks. Increasing `mhnsw_ef_search` shows whether a larger ANN "
            "candidate pool reduces that failure mode on this corpus."
        )
    else:
        finding = (
            "No filtered-ANN underfill was observed in this controlled "
            "selectivity window: "
            "every tested category had at least LIMIT eligible chunks and "
            "the indexed query "
            "returned LIMIT rows at every tested `mhnsw_ef_search` value. "
            "The exact-top-k "
            "overlap still quantifies approximation under the selective predicates."
        )

    lines.extend(
        [
            finding,
            "",
            f"Underfilled categories: **{' · '.join(underfill_parts)}**.",
            "",
            (
                "Mean overlap with index-ignored exact top-k: "
                f"**{' · '.join(overlap_parts)}**."
            ),
            "",
            "The index-ignored mode is used only as the exact comparison "
            "baseline and the ",
            "vector index is restored in a `finally` block after the experiment.",
            "",
            f"Artifact: `{artifact_path.as_posix()}`",
            "",
        ]
    )

    return "\n".join(lines)


async def run(
    *,
    query: str,
    limit: int,
    maximum_chunks: int,
    category_count: int,
    warmups: int,
    runs: int,
    ef_values: tuple[int, ...],
) -> Path:
    """Execute the selective-filter study and write JSON plus Markdown artifacts."""
    if limit <= 0 or maximum_chunks < limit:
        raise ValueError("limit must be positive and max eligible chunks >= limit.")
    if category_count <= 0 or runs <= 0 or warmups < 0:
        raise ValueError(
            "category-count/runs must be positive and warmups non-negative."
        )
    if not ef_values:
        raise ValueError("At least one mhnsw_ef_search value is required.")

    for value in ef_values:
        ef_sql(value)

    embedding = await EmbeddingService().embed_text(query)
    environment = await collect_environment()

    async with database_manager.session() as session:
        total_chunks, categories = await discover_categories(
            session,
            limit=limit,
            maximum_chunks=maximum_chunks,
            category_count=category_count,
        )

    await set_vector_index_ignored(ignored=False)
    indexed = await run_indexed(
        embedding=embedding,
        categories=categories,
        ef_values=ef_values,
        limit=limit,
        warmups=warmups,
        runs=runs,
    )

    try:
        await set_vector_index_ignored(ignored=True)
        exact = await run_exact(
            embedding=embedding,
            categories=categories,
            limit=limit,
            warmups=warmups,
            runs=runs,
        )
    finally:
        await set_vector_index_ignored(ignored=False)

    results = build_results(
        categories=categories,
        indexed=indexed,
        exact=exact,
        ef_values=ef_values,
        limit=limit,
    )

    underfilled_categories_by_ef = {
        str(ef): sum(
            1
            for result in results
            for observation in result.indexed
            if observation.ef_search == ef and observation.underfilled
        )
        for ef in ef_values
    }
    mean_exact_top_k_overlap_by_ef = {
        str(ef): statistics.mean(
            observation.exact_top_k_overlap
            for result in results
            for observation in result.indexed
            if observation.ef_search == ef
        )
        for ef in ef_values
    }

    study = SelectiveFilterStudy(
        executed_at=datetime.now(UTC).isoformat(),
        environment=environment,
        query=query,
        limit=limit,
        total_chunks=total_chunks,
        category_count=len(categories),
        minimum_eligible_chunks=limit,
        maximum_eligible_chunks=maximum_chunks,
        warmups=warmups,
        runs=runs,
        ef_values=ef_values,
        results=results,
        underfilled_categories_by_ef=underfilled_categories_by_ef,
        mean_exact_top_k_overlap_by_ef=mean_exact_top_k_overlap_by_ef,
    )

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"selective_filter_probe_{timestamp}.json"
    output_path.write_text(json.dumps(asdict(study), indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(study, output_path), encoding="utf-8")

    print(f"Categories tested: {len(categories)}")
    for ef_search in ef_values:
        print(
            f"ef={ef_search}: underfilled "
            f"{underfilled_categories_by_ef[str(ef_search)]}/{len(categories)}, "
            "mean exact top-k overlap "
            f"{mean_exact_top_k_overlap_by_ef[str(ef_search)] * 100:.1f}%"
        )
    print(f"Saved JSON to {output_path}")
    print(f"Saved report to {REPORT_PATH}")

    await database_manager.dispose()
    return output_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Probe highly selective category predicates for ANN underfill and "
            "compare indexed results with an index-ignored exact baseline."
        )
    )
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--max-eligible-chunks",
        type=int,
        default=DEFAULT_MAX_ELIGIBLE_CHUNKS,
    )
    parser.add_argument(
        "--category-count",
        type=int,
        default=DEFAULT_CATEGORY_COUNT,
    )
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument(
        "--ef-search",
        type=int,
        nargs="+",
        default=list(DEFAULT_EF_VALUES),
    )
    return parser.parse_args()


async def async_main() -> None:
    """Run the experiment from CLI arguments."""
    args = parse_args()
    await run(
        query=args.query,
        limit=args.limit,
        maximum_chunks=args.max_eligible_chunks,
        category_count=args.category_count,
        warmups=args.warmups,
        runs=args.runs,
        ef_values=tuple(args.ef_search),
    )


def main() -> None:
    """Run the async experiment entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
