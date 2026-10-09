"""Linked-search API integration tests."""

from fastapi.testclient import TestClient


def test_linked_search_returns_results(
    client: TestClient,
) -> None:
    """Linked search should restrict retrieval to outgoing links."""
    response = client.post(
        "/api/search/linked",
        json={
            "query": "neural network training",
            "source_title": "Machine learning",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["query"] == ("neural network training")
    assert payload["source_title"] == ("Machine learning")
    assert payload["results"]

    debug = payload["debug"]

    assert "article_links" in debug["sql"]
    assert "source.title = :source_title" in debug["sql"]

    assert debug["parameters"]["source_title"] == ("Machine learning")
    assert debug["parameters"]["limit"] == 5

    assert debug["embedding_ms"] >= 0
    assert debug["search_ms"] >= 0
    assert debug["explain_ms"] >= 0
    assert debug["total_ms"] >= debug["search_ms"]

    assert debug["execution_plan"]


def test_linked_search_rejects_empty_source_title(
    client: TestClient,
) -> None:
    """Linked search should reject an empty source title."""
    response = client.post(
        "/api/search/linked",
        json={
            "query": "neural network training",
            "source_title": "   ",
            "limit": 5,
        },
    )

    assert response.status_code == 422


def test_linked_search_rejects_empty_query(
    client: TestClient,
) -> None:
    """Linked search should reject an empty query."""
    response = client.post(
        "/api/search/linked",
        json={
            "query": "   ",
            "source_title": "Machine learning",
            "limit": 5,
        },
    )

    assert response.status_code == 422
