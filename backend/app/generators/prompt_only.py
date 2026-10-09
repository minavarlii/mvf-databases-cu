"""Prompt-only fallback text generator."""

from __future__ import annotations


class PromptOnlyGenerator:
    """Return the completed RAG prompt without calling an LLM."""

    async def generate(
        self,
        *,
        prompt: str,
    ) -> str:
        """Return the prompt unchanged.

        Args:
            prompt: Fully constructed RAG prompt.

        Returns:
            Prompt ready to be copied into an external LLM.
        """
        return prompt

    async def close(self) -> None:
        """Release generator resources."""
