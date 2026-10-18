"""Exercise UPDATE semantics for a MariaDB VECTOR column on an indexed table."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core import get_settings

TABLE_NAME = "vector_update_probe"
INDEX_NAME = "ix_vector_update_probe_embedding"

CREATE_TABLE_SQL = f"""
CREATE TABLE {TABLE_NAME} (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (id),
    VECTOR INDEX {INDEX_NAME} (embedding) M = 8 DISTANCE = cosine
) ENGINE=InnoDB
"""

SEARCH_SQL = f"""
SELECT id
FROM {TABLE_NAME}
ORDER BY VEC_DISTANCE_COSINE(
    embedding,
    VEC_FromText(:embedding)
) ASC
LIMIT 1
"""

DROP_INDEX_SQL = f"DROP INDEX {INDEX_NAME} ON {TABLE_NAME}"
CREATE_INDEX_SQL = f"""
CREATE VECTOR INDEX {INDEX_NAME}
ON {TABLE_NAME} (embedding)
M = 8
DISTANCE = cosine
"""


def one_hot(index: int) -> str:
    """Return a deterministic unit VECTOR(384) encoded as JSON."""
    values = [0.0] * 384
    values[index] = 1.0
    return json.dumps(values, separators=(",", ":"))


@pytest.mark.asyncio
async def test_vector_update_is_committed_and_searchable_after_index_rebuild() -> None:
    """Update an indexed vector, then verify storage and rebuilt ANN visibility.

    The test deliberately does not assume that an already-built HNSW graph must
    expose an UPDATE immediately. It first proves that the committed VECTOR value
    changed in InnoDB, then rebuilds the scratch VECTOR INDEX and verifies that ANN
    search uses the updated value. This keeps the test deterministic while still
    exercising UPDATE against a vector-indexed table.
    """
    before_embedding = one_hot(0)
    after_embedding = one_hot(1)
    distractor_a = one_hot(2)
    distractor_b = one_hot(3)

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
            await session.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
            await session.commit()
            await session.execute(text(CREATE_TABLE_SQL))
            await session.commit()

            try:
                await session.execute(
                    text(
                        f"""
                        INSERT INTO {TABLE_NAME} (embedding)
                        VALUES
                            (VEC_FromText(:before_embedding)),
                            (VEC_FromText(:distractor_a)),
                            (VEC_FromText(:distractor_b))
                        """
                    ),
                    {
                        "before_embedding": before_embedding,
                        "distractor_a": distractor_a,
                        "distractor_b": distractor_b,
                    },
                )
                await session.commit()

                probe_id = int(
                    await session.scalar(
                        text(SEARCH_SQL),
                        {"embedding": before_embedding},
                    )
                    or 0
                )
                assert probe_id > 0

                await session.execute(
                    text(
                        f"""
                        UPDATE {TABLE_NAME}
                        SET embedding = VEC_FromText(:embedding)
                        WHERE id = :probe_id
                        """
                    ),
                    {
                        "embedding": after_embedding,
                        "probe_id": probe_id,
                    },
                )
                await session.commit()

                old_distance = await session.scalar(
                    text(
                        f"""
                        SELECT VEC_DISTANCE_COSINE(
                            embedding,
                            VEC_FromText(:embedding)
                        )
                        FROM {TABLE_NAME}
                        WHERE id = :probe_id
                        """
                    ),
                    {
                        "embedding": before_embedding,
                        "probe_id": probe_id,
                    },
                )
                new_distance = await session.scalar(
                    text(
                        f"""
                        SELECT VEC_DISTANCE_COSINE(
                            embedding,
                            VEC_FromText(:embedding)
                        )
                        FROM {TABLE_NAME}
                        WHERE id = :probe_id
                        """
                    ),
                    {
                        "embedding": after_embedding,
                        "probe_id": probe_id,
                    },
                )
                assert float(old_distance or 0.0) > 0.9
                assert abs(float(new_distance or 0.0)) < 1e-6

                await session.execute(text(DROP_INDEX_SQL))
                await session.commit()
                await session.execute(text(CREATE_INDEX_SQL))
                await session.commit()

                rebuilt_top = await session.scalar(
                    text(SEARCH_SQL),
                    {"embedding": after_embedding},
                )
                assert int(rebuilt_top or 0) == probe_id
            finally:
                await session.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME}"))
                await session.commit()
    finally:
        await engine.dispose()
