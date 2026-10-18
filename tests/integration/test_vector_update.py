"""Verify that MariaDB's VECTOR INDEX reflects committed embedding updates."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core import get_settings

PROBE_PAGE_ID = -9_876_543_211
PROBE_TITLE = "MVF vector update probe"
SEARCH_SQL = """
SELECT id
FROM chunks
ORDER BY VEC_DISTANCE_COSINE(
    embedding,
    VEC_FromText(:embedding)
) ASC
LIMIT 1
"""


def one_hot(index: int) -> str:
    """Return a deterministic unit VECTOR(384) encoded as JSON."""
    values = [0.0] * 384
    values[index] = 1.0
    return json.dumps(values, separators=(",", ":"))


@pytest.mark.asyncio
async def test_vector_index_reflects_committed_embedding_update() -> None:
    """Update one stored vector and verify indexed nearest-neighbor visibility."""
    before_embedding = one_hot(0)
    after_embedding = one_hot(1)

    # Use a test-local engine with NullPool. Other integration tests exercise the
    # global FastAPI engine through TestClient/AnyIO event loops; reusing pooled
    # asyncmy connections across pytest event loops can otherwise attach a Future
    # to the wrong loop. This test needs database semantics, not shared pooling.
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text("DELETE FROM articles WHERE wikipedia_page_id = :page_id"),
                {"page_id": PROBE_PAGE_ID},
            )
            await session.commit()

            try:
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
                        "url": "https://example.invalid/mvf-vector-update-probe",
                        "content": "vector update index maintenance probe",
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
                        "content": "vector update index maintenance probe",
                        "embedding": before_embedding,
                    },
                )
                chunk_id = await session.scalar(text("SELECT LAST_INSERT_ID()"))
                assert chunk_id is not None
                await session.commit()

                before_top = await session.scalar(
                    text(SEARCH_SQL),
                    {"embedding": before_embedding},
                )
                assert int(before_top or 0) == int(chunk_id)

                await session.execute(
                    text(
                        """
                        UPDATE chunks
                        SET embedding = VEC_FromText(:embedding)
                        WHERE id = :chunk_id
                        """
                    ),
                    {
                        "embedding": after_embedding,
                        "chunk_id": int(chunk_id),
                    },
                )
                await session.commit()

                after_top = await session.scalar(
                    text(SEARCH_SQL),
                    {"embedding": after_embedding},
                )
                assert int(after_top or 0) == int(chunk_id)

                old_distance = await session.scalar(
                    text(
                        """
                        SELECT VEC_DISTANCE_COSINE(
                            embedding,
                            VEC_FromText(:embedding)
                        )
                        FROM chunks
                        WHERE id = :chunk_id
                        """
                    ),
                    {
                        "embedding": before_embedding,
                        "chunk_id": int(chunk_id),
                    },
                )
                new_distance = await session.scalar(
                    text(
                        """
                        SELECT VEC_DISTANCE_COSINE(
                            embedding,
                            VEC_FromText(:embedding)
                        )
                        FROM chunks
                        WHERE id = :chunk_id
                        """
                    ),
                    {
                        "embedding": after_embedding,
                        "chunk_id": int(chunk_id),
                    },
                )
                assert float(old_distance or 0.0) > 0.9
                assert abs(float(new_distance or 0.0)) < 1e-6
            finally:
                await session.execute(
                    text("DELETE FROM articles WHERE wikipedia_page_id = :page_id"),
                    {"page_id": PROBE_PAGE_ID},
                )
                await session.commit()
    finally:
        await engine.dispose()
