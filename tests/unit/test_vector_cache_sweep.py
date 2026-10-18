"""Unit checks for deterministic cache-sweep vector perturbations."""

from __future__ import annotations

import math

from experiments.vector_cache_sweep import perturb_embedding


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
