"""Semantic-search API integration tests."""

from fastapi.testclient import TestClient


def test_search_endpoint_returns_results(
    client: TestClient,
) -> None:
    """Semantic search should return ranked chunks."""
    response = client.post(
        "/api/search",
        json={
            "query": "machine learning",
            "limit": 3,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["query"] == "machine learning"
    assert len(payload["results"]) <= 3

    for result in payload["results"]:
        assert "chunk_id" in result
        assert "article_id" in result
        assert "article_title" in result
        assert "chunk_index" in result
        assert "content" in result
        assert "token_count" in result
        assert "distance" in result

    debug = payload["debug"]

    assert "VEC_DISTANCE_COSINE" in debug["sql"]
    assert debug["search_ms"] >= 0
    assert debug["embedding_ms"] >= 0
    assert debug["explain_ms"] >= 0
    assert debug["total_ms"] >= debug["search_ms"]
    assert debug["execution_plan"]

    assert any(row["key"] == "ix_chunks_embedding" for row in debug["execution_plan"])


def test_search_endpoint_rejects_empty_query(
    client: TestClient,
) -> None:
    """Semantic search should reject an empty query."""
    response = client.post(
        "/api/search",
        json={
            "query": "   ",
            "limit": 3,
        },
    )

    assert response.status_code == 422
