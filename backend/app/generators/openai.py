"""OpenAI text-generation provider."""

from __future__ import annotations

from typing import Any

import httpx


class OpenAIGenerator:
    """Generate RAG answers using the OpenAI Responses API."""

    API_URL = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Initialize the OpenAI generator.

        Args:
            api_key: OpenAI API key.
            model: OpenAI model identifier.
            timeout_seconds: HTTP request timeout.
        """
        normalized_api_key = api_key.strip()
        normalized_model = model.strip()

        if not normalized_api_key:
            raise ValueError("OpenAI API key must not be empty.")

        if not normalized_model:
            raise ValueError("OpenAI model must not be empty.")

        self._model = normalized_model

        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {normalized_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def generate(
        self,
        *,
        prompt: str,
    ) -> str:
        """Generate an answer from a completed RAG prompt.

        Args:
            prompt: Fully constructed grounded RAG prompt.

        Returns:
            Generated text response.

        Raises:
            RuntimeError: If the API response contains no text.
        """
        response = await self._client.post(
            self.API_URL,
            json={
                "model": self._model,
                "input": prompt,
            },
        )

        response.raise_for_status()

        payload: dict[str, Any] = response.json()

        output_text = self._extract_output_text(payload)

        if not output_text:
            raise RuntimeError("OpenAI response did not contain generated text.")

        return output_text

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> OpenAIGenerator:
        """Enter the asynchronous context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Exit the asynchronous context manager."""
        await self.close()

    @staticmethod
    def _extract_output_text(
        payload: dict[str, Any],
    ) -> str:
        """Extract generated text from a Responses API payload.

        Args:
            payload: OpenAI Responses API JSON payload.

        Returns:
            Concatenated generated text.
        """
        texts: list[str] = []

        for output_item in payload.get(
            "output",
            [],
        ):
            if output_item.get("type") != "message":
                continue

            for content_item in output_item.get(
                "content",
                [],
            ):
                if content_item.get("type") != "output_text":
                    continue

                text_value = content_item.get("text")

                if isinstance(text_value, str):
                    texts.append(text_value)

        return "\n".join(texts).strip()
