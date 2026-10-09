"""Article API integration tests."""

from fastapi.testclient import TestClient


def test_list_articles(
    client: TestClient,
) -> None:
    """Article endpoint should return paginated records."""
    response = client.get("/api/articles?limit=5&offset=0")

    assert response.status_code == 200

    payload = response.json()

    assert payload["limit"] == 5
    assert payload["offset"] == 0
    assert payload["total"] >= 100
    assert len(payload["items"]) <= 5

    article = payload["items"][0]

    assert "id" in article
    assert "wikipedia_page_id" in article
    assert "title" in article
    assert "url" in article
    assert "word_count" in article


def test_get_article(
    client: TestClient,
) -> None:
    """Article detail endpoint should return article metadata."""
    listing = client.get("/api/articles?limit=1")

    assert listing.status_code == 200

    article_id = listing.json()["items"][0]["id"]

    response = client.get(f"/api/articles/{article_id}")

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == article_id
    assert payload["title"]
    assert payload["content"]
    assert isinstance(
        payload["categories"],
        list,
    )


def test_missing_article_returns_404(
    client: TestClient,
) -> None:
    """Unknown article identifiers should return 404."""
    response = client.get("/api/articles/999999999")

    assert response.status_code == 404
