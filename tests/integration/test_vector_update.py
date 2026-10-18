"""Measure committed UPDATE visibility for a MariaDB VECTOR INDEX."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core import get_settings

CREATE_TABLE_SQL = """
CREATE TABLE vector_update_probe (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    embedding VECTOR(384) NOT NULL,
    PRIMARY KEY (id),
    VECTOR INDEX ix_vector_update_probe_embedding (embedding)
        M = 8
        DISTANCE = cosine
) ENGINE=InnoDB
"""

SEARCH_SQL = """
SELECT id
FROM vector_update_probe
ORDER BY VEC_DISTANCE_COSINE(
    embedding,
    VEC_FromText(:embedding)
) ASC
LIMIT 1
"""

UPDATE_SQL = """
UPDATE vector_update_probe
SET embedding = VEC_FromText(:embedding)
WHERE id = :probe_id
"""

DISTANCE_SQL = """
SELECT VEC_DISTANCE_COSINE(
    embedding,
    VEC_FromText(:embedding)
)
FROM vector_update_probe
WHERE id = :probe_id
"""

DROP_INDEX_SQL = """
DROP INDEX ix_vector_update_probe_embedding
ON vector_update_probe
"""

CREATE_INDEX_SQL = """
CREATE VECTOR INDEX ix_vector_update_probe_embedding
ON vector_update_probe (embedding)
M = 8
DISTANCE = cosine
"""


def one_hot(index: int) -> str:
    """Return a deterministic unit VECTOR(384) encoded as JSON."""
    values = [0.0] * 384
    values[index] = 1.0
    return json.dumps(values, separators=(",", ":"))


@pytest.mark.asyncio
async def test_vector_update_visibility_before_and_after_index_rebuild() -> None:
    """Measure ANN visibility of a committed in-place VECTOR update.

    On the MariaDB 11.8.9 configuration used by MVF, the committed VECTOR value
    is immediately visible both to ordinary SQL distance evaluation and to the
    already-built HNSW index in this controlled scratch-table probe. The test
    checks that visibility before rebuilding the index, then rebuilds it and
    verifies that the same updated vector remains searchable afterwards.
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
            await session.execute(text("DROP TABLE IF EXISTS vector_update_probe"))
            await session.commit()
            await session.execute(text(CREATE_TABLE_SQL))
            await session.commit()

            try:
                await session.execute(
                    text(
                        """
                        INSERT INTO vector_update_probe (embedding)
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
                    text(UPDATE_SQL),
                    {"embedding": after_embedding, "probe_id": probe_id},
                )
                await session.commit()

                old_distance = await session.scalar(
                    text(DISTANCE_SQL),
                    {"embedding": before_embedding, "probe_id": probe_id},
                )
                new_distance = await session.scalar(
                    text(DISTANCE_SQL),
                    {"embedding": after_embedding, "probe_id": probe_id},
                )
                assert float(old_distance or 0.0) > 0.9
                assert abs(float(new_distance or 0.0)) < 1e-6

                # Critical UPDATE observation: query the already-built HNSW
                # graph before any rebuild. On the verified MariaDB 11.8.9
                # scratch-table probe, the committed update is immediately visible.
                pre_rebuild_top = await session.scalar(
                    text(SEARCH_SQL),
                    {"embedding": after_embedding},
                )
                assert int(pre_rebuild_top or 0) == probe_id

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
                await session.execute(text("DROP TABLE IF EXISTS vector_update_probe"))
                await session.commit()
    finally:
        await engine.dispose()
