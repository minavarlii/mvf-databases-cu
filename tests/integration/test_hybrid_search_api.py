"""Hybrid-search API integration tests."""

from fastapi.testclient import TestClient


def test_hybrid_search_respects_category(
    client: TestClient,
) -> None:
    """Hybrid search should apply the relational category filter."""
    response = client.post(
        "/api/search/hybrid",
        json={
            "query": "image dataset",
            "category": "Datasets in computer vision",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["category"] == ("Datasets in computer vision")

    results = payload["results"]

    assert results

    assert all(
        result["article_title"] == "80 Million Tiny Images" for result in results
    )

    debug = payload["debug"]

    assert "article_categories" in debug["sql"]

    assert "WHERE cat.name = :category" in debug["sql"]

    assert debug["parameters"]["category"] == ("Datasets in computer vision")

    assert debug["search_ms"] >= 0
    assert debug["explain_ms"] >= 0
    assert debug["execution_plan"]


def test_hybrid_search_rejects_empty_category(
    client: TestClient,
) -> None:
    """Hybrid search should reject an empty category."""
    response = client.post(
        "/api/search/hybrid",
        json={
            "query": "image dataset",
            "category": "   ",
            "limit": 5,
        },
    )

    assert response.status_code == 422
