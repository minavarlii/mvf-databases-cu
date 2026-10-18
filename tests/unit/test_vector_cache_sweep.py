"""Unit checks for deterministic cache-sweep vector perturbations."""

from __future__ import annotations

import math

from experiments.vector_cache_sweep import (
    QueryMeasurement,
    RebuildMeasurement,
    mean_pairwise_overlap_within_setting,
    perturb_embedding,
)


def test_perturb_embedding_is_distinct_deterministic_and_norm_preserving() -> None:
    """Perturbed copies remove exact ties without changing cosine-vector norm."""
    source = [0.0] * 384
    source[7] = 0.6
    source[19] = 0.8

    first = perturb_embedding(source, source_chunk_id=123, copy_number=1)
    repeated = perturb_embedding(source, source_chunk_id=123, copy_number=1)
    second = perturb_embedding(source, source_chunk_id=123, copy_number=2)

    assert first == repeated
    assert first != source
    assert second != first
    assert math.isclose(
        math.sqrt(sum(value * value for value in first)),
        math.sqrt(sum(value * value for value in source)),
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def _query(question_id: str, ids: tuple[int, ...]) -> QueryMeasurement:
    return QueryMeasurement(
        question_id=question_id,
        mean_ms=1.0,
        median_ms=1.0,
        p95_ms=1.0,
        samples_ms=(1.0,),
        top5_ids=ids,
    )


def _rebuild(number: int, ids: tuple[int, ...]) -> RebuildMeasurement:
    return RebuildMeasurement(
        rebuild_number=number,
        index_build_time_ms=100.0,
        query_mean_ms=1.0,
        query_median_ms=1.0,
        query_p95_ms=1.0,
        overlap_with_first_rebuild_in_setting=1.0,
        queries=(_query("q1", ids),),
    )


def test_pairwise_overlap_excludes_self_reference() -> None:
    """Pairwise aggregation compares distinct rebuilds only."""
    rebuilds = [
        _rebuild(1, (1, 2, 3, 4, 5)),
        _rebuild(2, (1, 2, 3, 6, 7)),
        _rebuild(3, (1, 2, 8, 9, 10)),
    ]

    # Pair overlaps are 3/5, 2/5, and 2/5 -> mean 7/15.
    assert math.isclose(
        mean_pairwise_overlap_within_setting(rebuilds),
        7 / 15,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
