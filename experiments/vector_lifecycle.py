"""Probe transaction isolation and vector-index maintenance across row lifecycle."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from backend.app.db import database_manager
from backend.app.db.queries import VectorQueries
from backend.app.services import EmbeddingService
from experiments.environment import collect_environment

RESULTS_DIRECTORY = Path("experiments/results")

INSERT_ARTICLE_SQL = """
INSERT INTO articles (
    wikipedia_page_id,
    revision_id,
    title,
    url,
    summary,
    content,
    word_count
)
VALUES (
    :page_id,
    :revision_id,
    :title,
    :url,
    :summary,
    :content,
    :word_count
)
"""

INSERT_CHUNK_SQL = """
INSERT INTO chunks (
    article_id,
    chunk_index,
    content,
    token_count,
    embedding
)
VALUES (
    :article_id,
    0,
    :content,
    :token_count,
    VEC_FromText(:embedding)
)
"""

COUNT_ARTICLE_SQL = """
SELECT COUNT(*)
FROM articles
WHERE title = :title
"""

DELETE_ARTICLE_SQL = """
DELETE FROM articles
WHERE id = :article_id
"""

COUNT_CHUNKS_SQL = """
SELECT COUNT(*)
FROM chunks
WHERE article_id = :article_id
"""

LAST_INSERT_ID_SQL = """
SELECT LAST_INSERT_ID()
"""


async def main() -> None:
    """Exercise insert, isolation, ANN visibility, cascade delete, and cleanup."""
    token = uuid4().hex
    title = f"MVF vector lifecycle probe {token}"
    content = (
        "Synthetic MariaDB vector lifecycle probe used only for a controlled "
        "transaction and index-maintenance experiment."
    )
    embedding = await EmbeddingService().embed_text(content)
    embedding_text = json.dumps(embedding)
    environment = await collect_environment()

    article_id: int | None = None
    before_commit_visible = False
    after_commit_visible = False
    ann_found_after_commit = False
    after_delete_article_count = -1
    after_delete_chunk_count = -1
    insert_commit_ms = 0.0
    delete_commit_ms = 0.0

    try:
        writer = database_manager.session()
        async with writer as writer_session:
            await writer_session.execute(
                text(INSERT_ARTICLE_SQL),
                {
                    "page_id": 9_000_000_000 + int(token[:6], 16),
                    "revision_id": int(token[6:14], 16),
                    "title": title,
                    "url": f"https://example.invalid/{token}",
                    "summary": "Synthetic lifecycle probe",
                    "content": content,
                    "word_count": len(content.split()),
                },
            )

            inserted_id = await writer_session.scalar(text(LAST_INSERT_ID_SQL))

            if inserted_id is None:
                raise RuntimeError("MariaDB did not return LAST_INSERT_ID().")

            article_id = int(inserted_id)

            await writer_session.execute(
                text(INSERT_CHUNK_SQL),
                {
                    "article_id": article_id,
                    "content": content,
                    "token_count": len(content.split()),
                    "embedding": embedding_text,
                },
            )

            async with database_manager.session() as observer_session:
                observed = await observer_session.scalar(
                    text(COUNT_ARTICLE_SQL),
                    {"title": title},
                )
                before_commit_visible = bool(observed)

            started = time.perf_counter()
            await writer_session.commit()
            insert_commit_ms = (time.perf_counter() - started) * 1000.0

        async with database_manager.session() as observer_session:
            observed = await observer_session.scalar(
                text(COUNT_ARTICLE_SQL),
                {"title": title},
            )
            after_commit_visible = bool(observed)

            vector_queries = VectorQueries(observer_session)
            results = await vector_queries.semantic_search(
                embedding=embedding,
                limit=10,
            )
            ann_found_after_commit = any(
                item.article_title == title for item in results
            )

        async with database_manager.session() as delete_session:
            started = time.perf_counter()
            await delete_session.execute(
                text(DELETE_ARTICLE_SQL),
                {"article_id": article_id},
            )
            await delete_session.commit()
            delete_commit_ms = (time.perf_counter() - started) * 1000.0

        async with database_manager.session() as observer_session:
            after_delete_article_count = int(
                await observer_session.scalar(
                    text(COUNT_ARTICLE_SQL),
                    {"title": title},
                )
                or 0
            )
            after_delete_chunk_count = int(
                await observer_session.scalar(
                    text(COUNT_CHUNKS_SQL),
                    {"article_id": article_id},
                )
                or 0
            )

    finally:
        if article_id is not None:
            async with database_manager.session() as cleanup_session:
                await cleanup_session.execute(
                    text(DELETE_ARTICLE_SQL),
                    {"article_id": article_id},
                )
                await cleanup_session.commit()
        await database_manager.dispose()

    payload = {
        "executed_at": datetime.now(UTC).isoformat(),
        "environment": asdict(environment),
        "probe": {
            "uncommitted_row_visible_to_second_session": before_commit_visible,
            "row_visible_after_commit": after_commit_visible,
            "vector_search_finds_row_after_commit": ann_found_after_commit,
            "article_rows_after_delete": after_delete_article_count,
            "chunk_rows_after_cascade_delete": after_delete_chunk_count,
            "insert_and_index_commit_ms": insert_commit_ms,
            "delete_and_index_commit_ms": delete_commit_ms,
        },
    }

    if before_commit_visible:
        raise RuntimeError("Second session observed uncommitted vector-bearing row.")
    if not after_commit_visible:
        raise RuntimeError("Committed article was not visible to a fresh session.")
    if not ann_found_after_commit:
        raise RuntimeError("Committed vector was not visible to semantic search.")
    if after_delete_article_count != 0 or after_delete_chunk_count != 0:
        raise RuntimeError("Delete/cascade cleanup left rows behind.")

    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIRECTORY / f"vector_lifecycle_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print("Uncommitted visible to second session: False")
    print("Visible after commit: True")
    print("Found by vector search after commit: True")
    print("Rows after delete: 0 article / 0 chunks")
    print(f"Insert+index commit: {insert_commit_ms:.3f} ms")
    print(f"Delete+index commit: {delete_commit_ms:.3f} ms")
    print(f"Saved results to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
