"""Export the current MariaDB corpus, including vectors, as portable gzip JSON."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.db import database_manager

DEFAULT_OUTPUT = Path("data/prebuilt/mvf_corpus.json.gz")

TABLE_QUERIES = {
    "articles": """
        SELECT id, wikipedia_page_id, revision_id, title, url, summary, content,
               word_count, created_at, updated_at
        FROM articles ORDER BY id
    """,
    "categories": """
        SELECT id, name, created_at, updated_at
        FROM categories ORDER BY id
    """,
    "article_categories": """
        SELECT article_id, category_id
        FROM article_categories ORDER BY article_id, category_id
    """,
    "article_links": """
        SELECT source_article_id, target_article_id
        FROM article_links ORDER BY source_article_id, target_article_id
    """,
    "chunks": """
        SELECT id, article_id, chunk_index, content, token_count,
               VEC_ToText(embedding) AS embedding,
               created_at, updated_at
        FROM chunks ORDER BY id
    """,
}


def json_value(value: Any) -> Any:
    """Convert SQL values to JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def parse_args() -> argparse.Namespace:
    """Parse export options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


async def export_snapshot(path: Path) -> dict[str, int]:
    """Export all corpus tables while preserving vector text exactly."""
    payload: dict[str, Any] = {
        "format": "mvf-prebuilt-v1",
        "tables": {},
    }
    counts: dict[str, int] = {}

    async with database_manager.session() as session:
        version = await session.scalar(text("SELECT VERSION()"))
        payload["mariadb_version"] = str(version)

        for table, query in TABLE_QUERIES.items():
            result = await session.execute(text(query))
            rows = [
                {key: json_value(value) for key, value in row.items()}
                for row in result.mappings()
            ]
            payload["tables"][table] = rows
            counts[table] = len(rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)

    return counts


async def async_main() -> None:
    """Export the snapshot selected by command-line arguments."""
    args = parse_args()
    counts = await export_snapshot(args.output)
    for table, count in counts.items():
        print(f"Exported {table}: {count} rows")
    print(f"Saved portable prebuilt corpus to {args.output}")
    await database_manager.dispose()


def main() -> None:
    """Run the exporter."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
