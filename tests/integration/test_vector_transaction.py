"""Verify relational rows and native vectors share one transaction."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from backend.app.db import database_manager

PROBE_PAGE_ID = -9_876_543_210
PROBE_TITLE = "MVF transaction rollback probe"


@pytest.mark.asyncio
async def test_article_and_vector_chunk_roll_back_together() -> None:
    """Roll back an article and its VECTOR(384) chunk atomically."""
    value = 1.0 / (384**0.5)
    embedding_json = json.dumps([value] * 384, separators=(",", ":"))

    async with database_manager.session() as session:
        await session.execute(
            text(
                """
                DELETE FROM articles
                WHERE wikipedia_page_id = :page_id
                """
            ),
            {"page_id": PROBE_PAGE_ID},
        )
        await session.commit()

    async with database_manager.session() as session:
        await session.execute(
            text(
                """
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
                    1,
                    :title,
                    :url,
                    NULL,
                    :content,
                    4
                )
                """
            ),
            {
                "page_id": PROBE_PAGE_ID,
                "title": PROBE_TITLE,
                "url": "https://example.invalid/mvf-transaction-probe",
                "content": "transaction rollback vector probe",
            },
        )

        article_id = await session.scalar(text("SELECT LAST_INSERT_ID()"))
        assert article_id is not None

        await session.execute(
            text(
                """
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
                    4,
                    VEC_FromText(:embedding)
                )
                """
            ),
            {
                "article_id": int(article_id),
                "content": "transaction rollback vector probe",
                "embedding": embedding_json,
            },
        )

        article_count = await session.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM articles
                WHERE wikipedia_page_id = :page_id
                """
            ),
            {"page_id": PROBE_PAGE_ID},
        )
        chunk_count = await session.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM chunks
                WHERE article_id = :article_id
                """
            ),
            {"article_id": int(article_id)},
        )

        assert article_count == 1
        assert chunk_count == 1

        await session.rollback()

    async with database_manager.session() as session:
        article_count = await session.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM articles
                WHERE wikipedia_page_id = :page_id
                """
            ),
            {"page_id": PROBE_PAGE_ID},
        )
        chunk_count = await session.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM chunks AS c
                INNER JOIN articles AS a
                    ON a.id = c.article_id
                WHERE a.wikipedia_page_id = :page_id
                """
            ),
            {"page_id": PROBE_PAGE_ID},
        )

    assert article_count == 0
    assert chunk_count == 0
