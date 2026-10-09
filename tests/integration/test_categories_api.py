"""Category API integration tests."""

from fastapi.testclient import TestClient


def test_list_categories(
    client: TestClient,
) -> None:
    """Category endpoint should return category metadata."""
    response = client.get("/api/categories")

    assert response.status_code == 200

    payload = response.json()

    assert payload["items"]

    category = payload["items"][0]

    assert "id" in category
    assert "name" in category
    assert "article_count" in category


def test_machine_learning_category_exists(
    client: TestClient,
) -> None:
    """Dataset should expose the Machine learning category."""
    response = client.get("/api/categories")

    assert response.status_code == 200

    names = {category["name"] for category in response.json()["items"]}

    assert "Machine learning" in names
