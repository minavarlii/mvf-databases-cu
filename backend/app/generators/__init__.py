"""Text-generation implementations."""

from backend.app.generators.openai import OpenAIGenerator
from backend.app.generators.prompt_only import PromptOnlyGenerator

__all__ = [
    "OpenAIGenerator",
    "PromptOnlyGenerator",
]
