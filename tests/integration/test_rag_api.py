"""RAG API integration tests."""

from fastapi.testclient import TestClient


def test_rag_endpoint_returns_answer_and_sources(
    client: TestClient,
) -> None:
    """RAG endpoint should return an answer and sources."""
    response = client.post(
        "/api/rag",
        json={
            "question": ("How does federated learning work?"),
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["question"] == ("How does federated learning work?")

    assert payload["answer"] == ("Test generated answer [Source 1].")

    assert len(payload["sources"]) <= 3

    debug = payload["debug"]

    assert "VEC_DISTANCE_COSINE" in debug["sql"]
    assert debug["search_ms"] >= 0
    assert debug["embedding_ms"] >= 0
    assert debug["execution_plan"]


def test_rag_endpoint_rejects_empty_question(
    client: TestClient,
) -> None:
    """RAG endpoint should reject an empty question."""
    response = client.post(
        "/api/rag",
        json={
            "question": "   ",
            "top_k": 3,
        },
    )

    assert response.status_code == 422
