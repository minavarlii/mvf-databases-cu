"""Restore a portable MVF corpus snapshot into an initialized MariaDB schema."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text

from backend.app.db import analyze_core_tables, database_manager

DEFAULT_INPUT = Path("data/prebuilt/mvf_corpus.json.gz")

DELETE_SQL = (
    "DELETE FROM chunks",
    "DELETE FROM article_links",
    "DELETE FROM article_categories",
    "DELETE FROM categories",
    "DELETE FROM articles",
)

INSERT_ARTICLE_SQL = """
INSERT INTO articles (
    id, wikipedia_page_id, revision_id, title, url, summary, content,
    word_count, created_at, updated_at
)
VALUES (
    :id, :wikipedia_page_id, :revision_id, :title, :url, :summary, :content,
    :word_count, :created_at, :updated_at
)
""".strip()

INSERT_CATEGORY_SQL = """
INSERT INTO categories (id, name, created_at, updated_at)
VALUES (:id, :name, :created_at, :updated_at)
""".strip()

INSERT_ARTICLE_CATEGORY_SQL = """
INSERT INTO article_categories (article_id, category_id)
VALUES (:article_id, :category_id)
""".strip()

INSERT_ARTICLE_LINK_SQL = """
INSERT INTO article_links (source_article_id, target_article_id)
VALUES (:source_article_id, :target_article_id)
""".strip()

INSERT_CHUNK_SQL = """
INSERT INTO chunks (
    id, article_id, chunk_index, content, token_count, embedding,
    created_at, updated_at
)
VALUES (
    :id, :article_id, :chunk_index, :content, :token_count,
    VEC_FromText(:embedding), :created_at, :updated_at
)
""".strip()


def parse_args() -> argparse.Namespace:
    """Parse restore options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    """Load and validate a portable snapshot."""
    if not path.exists():
        raise FileNotFoundError(
            f"Prebuilt corpus not found: {path}. Run `make prebuilt-export` first."
        )
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        raw_payload = json.load(handle)
    if not isinstance(raw_payload, dict):
        raise ValueError("Prebuilt corpus root must be a JSON object.")
    payload = cast(dict[str, Any], raw_payload)
    if payload.get("format") != "mvf-prebuilt-v1":
        raise ValueError("Unsupported prebuilt corpus format.")
    return payload


async def execute_many(
    session: Any,
    statement: str,
    rows: list[dict[str, Any]],
) -> None:
    """Execute one static INSERT for zero or more parameter rows."""
    if rows:
        await session.execute(text(statement), rows)


async def async_main() -> None:
    """Replace current corpus rows with the portable snapshot."""
    args = parse_args()
    payload = load_payload(args.input)
    tables = payload["tables"]

    async with database_manager.session() as session:
        for statement in DELETE_SQL:
            await session.execute(text(statement))

        await execute_many(session, INSERT_ARTICLE_SQL, tables["articles"])
        await execute_many(session, INSERT_CATEGORY_SQL, tables["categories"])
        await execute_many(
            session,
            INSERT_ARTICLE_CATEGORY_SQL,
            tables["article_categories"],
        )
        await execute_many(session, INSERT_ARTICLE_LINK_SQL, tables["article_links"])
        await execute_many(session, INSERT_CHUNK_SQL, tables["chunks"])
        await session.commit()
        await analyze_core_tables(session)
        await session.commit()

    print(
        "Restored prebuilt corpus: "
        f"{len(tables['articles'])} articles, "
        f"{len(tables['chunks'])} vectors, "
        f"{len(tables['article_links'])} links."
    )
    await database_manager.dispose()


def main() -> None:
    """Run the restore operation."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
