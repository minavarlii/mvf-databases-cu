"""Text chunking service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from backend.app.core.constants import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    EMBEDDING_MODEL_NAME,
)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """Represent one token-based chunk of article text."""

    index: int
    content: str
    token_count: int


class ChunkingService:
    """Split text into overlapping token-based chunks."""

    def __init__(
        self,
        *,
        model_name: str = EMBEDDING_MODEL_NAME,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        """Initialize the chunking service.

        Args:
            model_name: Tokenizer model identifier.
            chunk_size: Maximum number of tokens per chunk.
            chunk_overlap: Number of tokens shared by adjacent chunks.

        Raises:
            ValueError: If the chunking configuration is invalid.
        """
        if chunk_size <= 0:
            raise ValueError("Chunk size must be greater than zero.")

        if chunk_overlap < 0:
            raise ValueError("Chunk overlap cannot be negative.")

        if chunk_overlap >= chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")

        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

        self._tokenizer: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(
            model_name
        )

    def chunk(self, text: str) -> list[TextChunk]:
        """Split text into overlapping token chunks.

        Args:
            text: Source article text.

        Returns:
            Ordered chunks containing decoded text and token counts.
        """
        normalized_text = text.strip()

        if not normalized_text:
            return []

        token_ids = self._tokenizer.encode(
            normalized_text,
            add_special_tokens=False,
            verbose=False,
        )

        chunks: list[TextChunk] = []
        step = self._chunk_size - self._chunk_overlap

        for index, start in enumerate(range(0, len(token_ids), step)):
            chunk_token_ids = token_ids[start : start + self._chunk_size]

            if not chunk_token_ids:
                break

            decoded_content = cast(
                str,
                self._tokenizer.decode(
                    chunk_token_ids,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=True,
                ),
            )

            content = decoded_content.strip()

            if not content:
                continue

            chunks.append(
                TextChunk(
                    index=index,
                    content=content,
                    token_count=len(chunk_token_ids),
                )
            )

            if start + self._chunk_size >= len(token_ids):
                break

        return chunks
