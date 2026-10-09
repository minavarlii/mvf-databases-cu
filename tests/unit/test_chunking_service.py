"""Tests for the text chunking service."""

import pytest

from backend.app.services import ChunkingService


def test_empty_text_produces_no_chunks() -> None:
    """Empty text should not produce chunks."""
    service = ChunkingService()

    assert service.chunk("") == []
    assert service.chunk("   ") == []


def test_short_text_produces_single_chunk() -> None:
    """Short text should fit into a single chunk."""
    service = ChunkingService(
        chunk_size=20,
        chunk_overlap=5,
    )

    chunks = service.chunk("Machine learning allows computers to learn from data.")

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content
    assert chunks[0].token_count <= 20


def test_long_text_produces_multiple_chunks() -> None:
    """Long text should be divided into multiple chunks."""
    service = ChunkingService(
        chunk_size=20,
        chunk_overlap=5,
    )

    text = " ".join(f"machine learning sentence number {index}" for index in range(100))

    chunks = service.chunk(text)

    assert len(chunks) > 1

    assert all(chunk.token_count <= 20 for chunk in chunks)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (-1, 0),
        (10, -1),
        (10, 10),
        (10, 11),
    ],
)
def test_invalid_configuration_raises_value_error(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    """Invalid chunking configuration should be rejected."""
    with pytest.raises(ValueError):
        ChunkingService(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
