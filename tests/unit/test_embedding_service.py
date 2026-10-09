"""Tests for the embedding service."""

import pytest

from backend.app.core.constants import EMBEDDING_DIMENSIONS
from backend.app.services import EmbeddingService


@pytest.mark.asyncio
async def test_embed_text_returns_expected_dimensions() -> None:
    """Single-text embedding should have the configured dimensions."""
    service = EmbeddingService()

    embedding = await service.embed_text("Machine learning learns patterns from data.")

    assert len(embedding) == EMBEDDING_DIMENSIONS
    assert all(isinstance(value, float) for value in embedding)


@pytest.mark.asyncio
async def test_embed_many_preserves_input_count() -> None:
    """Batch embedding should preserve the number of inputs."""
    service = EmbeddingService()

    embeddings = await service.embed_many(
        [
            "Machine learning uses data.",
            "Neural networks contain layers.",
            "Gradient descent optimizes parameters.",
        ]
    )

    assert len(embeddings) == 3

    assert all(len(embedding) == EMBEDDING_DIMENSIONS for embedding in embeddings)


@pytest.mark.asyncio
async def test_empty_text_is_rejected() -> None:
    """Empty text should not be embedded."""
    service = EmbeddingService()

    with pytest.raises(ValueError):
        await service.embed_text("   ")


@pytest.mark.asyncio
async def test_empty_batch_is_rejected() -> None:
    """Empty batches should be rejected."""
    service = EmbeddingService()

    with pytest.raises(ValueError):
        await service.embed_many([])
