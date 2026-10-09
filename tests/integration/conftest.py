"""Shared FastAPI integration-test fixtures."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_embedding_service,
    get_text_generator,
)
from backend.app.main import app


class FakeEmbeddingService:
    """Provide deterministic embeddings for API tests."""

    async def embed_text(
        self,
        text: str,
    ) -> list[float]:
        """Return a deterministic normalized embedding."""
        del text

        value = 1.0 / (384**0.5)

        return [value] * 384


class FakeTextGenerator:
    """Provide deterministic generated answers."""

    async def generate(
        self,
        *,
        prompt: str,
    ) -> str:
        """Return a stable fake generated answer."""
        del prompt

        return "Test generated answer [Source 1]."

    async def close(self) -> None:
        """Release fake generator resources."""


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a FastAPI test client with mocked AI dependencies."""
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()

    app.dependency_overrides[get_text_generator] = lambda: FakeTextGenerator()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
