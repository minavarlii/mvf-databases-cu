"""Build and maintain vector indexes for stored Wikipedia articles."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from backend.app.db import database_manager
from backend.app.db.models import Article
from backend.app.services import (
    ChunkingService,
    EmbeddingService,
    IndexingResult,
    IndexingService,
)


@dataclass(slots=True)
class IndexingSummary:
    """Track indexing statistics for one run."""

    scanned: int = 0
    indexed: int = 0
    rebuilt: int = 0
    skipped: int = 0
    empty: int = 0
    cleared: int = 0
    chunks_written: int = 0

    def record(
        self,
        result: IndexingResult,
    ) -> None:
        """Record one article indexing result."""
        self.scanned += 1

        if result.status == "indexed":
            self.indexed += 1
            self.chunks_written += result.chunk_count

        elif result.status == "rebuilt":
            self.rebuilt += 1
            self.chunks_written += result.chunk_count

        elif result.status == "skipped":
            self.skipped += 1

        elif result.status == "empty":
            self.empty += 1

        elif result.status == "cleared":
            self.cleared += 1


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Build or repair MariaDB vector indexes for stored articles.")
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of articles to scan. By default all articles are processed."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=("Rebuild vectors even when existing chunks are already valid."),
    )

    return parser.parse_args()


async def run(
    *,
    limit: int | None,
    force: bool,
) -> IndexingSummary:
    """Build or repair article vector indexes.

    Args:
        limit: Optional maximum number of articles to scan.
        force: Whether to rebuild already valid article indexes.

    Returns:
        Summary of the indexing run.

    Raises:
        ValueError: If limit is invalid.
    """
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be greater than zero.")

    chunking_service = ChunkingService()

    embedding_service = EmbeddingService()

    summary = IndexingSummary()

    async with database_manager.session() as session:
        statement = select(Article).order_by(Article.id)

        if limit is not None:
            statement = statement.limit(limit)

        query_result = await session.execute(statement)

        articles = list(query_result.scalars().all())

        indexing_service = IndexingService(
            session=session,
            chunking_service=chunking_service,
            embedding_service=embedding_service,
        )

        total_articles = len(articles)

        for position, article in enumerate(
            articles,
            start=1,
        ):
            try:
                result = await indexing_service.index_article(
                    article,
                    force=force,
                )

                await session.commit()

            except Exception:
                await session.rollback()
                raise

            summary.record(result)

            print(
                f"[{position}/{total_articles}] "
                f"{result.status.upper():<7} "
                f"{result.article_title} "
                f"({result.chunk_count} chunks)"
            )

    return summary


def print_summary(
    summary: IndexingSummary,
) -> None:
    """Print indexing-run statistics."""
    print()
    print("Vector indexing completed")
    print(f"Articles scanned:  {summary.scanned}")
    print(f"Indexed now:      {summary.indexed}")
    print(f"Rebuilt:          {summary.rebuilt}")
    print(f"Already valid:    {summary.skipped}")
    print(f"Empty articles:   {summary.empty}")
    print(f"Stale cleared:    {summary.cleared}")
    print(f"Chunks written:   {summary.chunks_written}")


async def main() -> None:
    """Run the vector-indexing command."""
    arguments = parse_arguments()

    try:
        summary = await run(
            limit=arguments.limit,
            force=arguments.force,
        )

        print_summary(summary)

    finally:
        await database_manager.dispose()


if __name__ == "__main__":
    asyncio.run(main())
