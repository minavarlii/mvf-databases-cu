"""Integration tests for the guided MariaDB vector-search demo."""

from __future__ import annotations

import json

import pytest

from scripts import demo


class FakeEmbeddingService:
    """Provide deterministic 384-dimensional embeddings for the demo test."""

    async def embed_text(
        self,
        text: str,
    ) -> list[float]:
        """Return a stable normalized embedding."""
        del text

        value = 1.0 / (384**0.5)
        return [value] * 384


@pytest.mark.asyncio
async def test_demo_json_exposes_mariadb_vector_workflows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The demo should expose semantic, hybrid, and linked MariaDB search."""
    monkeypatch.setattr(
        demo,
        "EmbeddingService",
        FakeEmbeddingService,
    )

    await demo.run(
        query="machine learning",
        category="Machine learning",
        source_title="Machine learning",
        limit=3,
        output_json=True,
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    database = payload["database"]

    assert database["version"]
    assert database["articles"] >= 1
    assert database["vectors"] >= 1
    assert database["vector_index"] is not None
    assert database["vector_index"]["name"] == "ix_chunks_embedding"

    searches = payload["searches"]

    assert [search["mode"] for search in searches] == [
        "semantic search",
        "hybrid search",
        "linked search",
    ]

    semantic, hybrid, linked = searches

    assert "VEC_DISTANCE_COSINE" in semantic["sql"]
    assert "VEC_DISTANCE_COSINE" in hybrid["sql"]
    assert "VEC_DISTANCE_COSINE" in linked["sql"]

    assert hybrid["category"] == "Machine learning"
    assert linked["source_title"] == "Machine learning"

    assert semantic["execution_plan"]
    assert hybrid["execution_plan"]
    assert linked["execution_plan"]

    assert any(
        row["key"] == "ix_chunks_embedding" for row in semantic["execution_plan"]
    )
    assert any(
        row["key"]
        in {
            "ix_chunks_embedding",
            "ix_chunks_article_id",
            "fk_article_categories_category",
            "uq_categories_name",
        }
        for row in hybrid["execution_plan"]
    )

    for search in searches:
        assert search["timings_ms"]["embedding"] >= 0
        assert search["timings_ms"]["search"] >= 0
        assert search["timings_ms"]["explain"] >= 0
        assert search["timings_ms"]["total"] >= search["timings_ms"]["search"]
