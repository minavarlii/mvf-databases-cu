"""Text embedding service."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sentence_transformers import SentenceTransformer

from backend.app.core.constants import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
)


class EmbeddingService:
    """Generate semantic text embeddings."""

    def __init__(
        self,
        *,
        model_name: str = EMBEDDING_MODEL_NAME,
    ) -> None:
        """Initialize the embedding model.

        Args:
            model_name: Sentence-transformers model identifier.
        """
        self._model = SentenceTransformer(model_name)

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        Args:
            text: Input text.

        Returns:
            Dense embedding vector.

        Raises:
            ValueError: If the input text is empty.
            RuntimeError: If the embedding dimensionality is unexpected.
        """
        normalized_text = text.strip()

        if not normalized_text:
            raise ValueError("Text must not be empty.")

        embeddings = await self.embed_many([normalized_text])

        return embeddings[0]

    async def embed_many(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: Input texts.

        Returns:
            Embeddings in the same order as the input texts.

        Raises:
            ValueError: If no texts are supplied or any text is empty.
            RuntimeError: If the embedding dimensionality is unexpected.
        """
        if not texts:
            raise ValueError("At least one text is required.")

        normalized_texts = [text.strip() for text in texts]

        if any(not text for text in normalized_texts):
            raise ValueError("Embedding texts must not be empty.")

        embeddings = await asyncio.to_thread(
            self._model.encode,
            normalized_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        result = [embedding.astype(float).tolist() for embedding in embeddings]

        self._validate_dimensions(result)

        return result

    @staticmethod
    def _validate_dimensions(
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Validate embedding dimensionality.

        Args:
            embeddings: Generated embedding vectors.

        Raises:
            RuntimeError: If an embedding has an unexpected size.
        """
        invalid_dimensions = [
            len(embedding)
            for embedding in embeddings
            if len(embedding) != EMBEDDING_DIMENSIONS
        ]

        if invalid_dimensions:
            raise RuntimeError(
                "Unexpected embedding dimensions: "
                f"expected {EMBEDDING_DIMENSIONS}, "
                f"received {invalid_dimensions}."
            )
