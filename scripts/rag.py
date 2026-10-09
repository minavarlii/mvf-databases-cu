"""Run the MVF retrieval-augmented generation pipeline."""

import argparse
import asyncio

from backend.app.core import get_settings
from backend.app.db import database_manager
from backend.app.generators import (
    OpenAIGenerator,
    PromptOnlyGenerator,
)
from backend.app.services import (
    EmbeddingService,
    RagService,
    TextGenerator,
)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the MVF RAG pipeline.",
    )

    parser.add_argument(
        "question",
        help="Natural-language question.",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of retrieved chunks used as context.",
    )

    parser.add_argument(
        "--generator",
        choices=(
            "prompt",
            "openai",
        ),
        default="prompt",
        help="Text-generation backend.",
    )

    return parser.parse_args()


def create_generator(
    generator_name: str,
) -> TextGenerator:
    """Create the requested text generator.

    Args:
        generator_name: Generator backend name.

    Returns:
        Configured text generator.

    Raises:
        ValueError: If OpenAI configuration is missing.
    """
    if generator_name == "prompt":
        return PromptOnlyGenerator()

    settings = get_settings()

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when --generator openai is used.")

    return OpenAIGenerator(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )


async def run(
    *,
    question: str,
    top_k: int,
    generator_name: str,
) -> None:
    """Run one RAG query.

    Args:
        question: Natural-language question.
        top_k: Number of retrieved context chunks.
        generator_name: Text-generation backend.
    """
    embedding_service = EmbeddingService()

    generator = create_generator(generator_name)

    try:
        async with database_manager.session() as session:
            rag_service = RagService(
                session=session,
                embedding_service=embedding_service,
                generator=generator,
            )

            result = await rag_service.answer(
                question,
                top_k=top_k,
            )
    finally:
        await generator.close()
        await database_manager.dispose()

    print()
    print("Answer:")
    print(result.answer)

    print()
    print("Sources:")

    for index, source in enumerate(
        result.sources,
        start=1,
    ):
        print(
            f"[{index}] {source.article_title} "
            f"(chunk={source.chunk_index}, "
            f"distance={source.distance:.6f})"
        )


async def main() -> None:
    """Run the RAG command."""
    arguments = parse_arguments()

    await run(
        question=arguments.question,
        top_k=arguments.top_k,
        generator_name=arguments.generator,
    )


if __name__ == "__main__":
    asyncio.run(main())
