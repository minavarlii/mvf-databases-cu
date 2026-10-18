"""Exercise portable snapshot export and destructive restore as one round trip."""

from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.core import get_settings
from backend.app.db import database_manager
from scripts.export_prebuilt import export_snapshot
from scripts.restore_prebuilt import load_payload, restore_snapshot

COUNT_SQL = {
    "articles": "SELECT COUNT(*) FROM articles",
    "categories": "SELECT COUNT(*) FROM categories",
    "article_categories": "SELECT COUNT(*) FROM article_categories",
    "article_links": "SELECT COUNT(*) FROM article_links",
    "chunks": "SELECT COUNT(*) FROM chunks",
}


async def database_counts() -> dict[str, int]:
    """Return row counts for all tables covered by the snapshot."""
    counts: dict[str, int] = {}
    async with database_manager.session() as session:
        for table, statement in COUNT_SQL.items():
            counts[table] = int(await session.scalar(text(statement)) or 0)
    return counts


@pytest.mark.asyncio
async def test_prebuilt_export_restore_roundtrip(tmp_path: Path) -> None:
    """Export the active corpus, restore it, and preserve every table count."""
    snapshot = tmp_path / "roundtrip.json.gz"

    try:
        before = await database_counts()

        exported = await export_snapshot(snapshot)
        payload = load_payload(snapshot)
        assert exported == before
        assert payload["format"] == "mvf-prebuilt-v1"

        restored = await restore_snapshot(
            snapshot,
            confirm_reset=True,
            expected_database=get_settings().db_name,
        )
        after = await database_counts()

        assert restored == before
        assert after == before
    finally:
        # This test runs under pytest-asyncio, while later FastAPI TestClient
        # fixtures create their own AnyIO event loop. Drop pooled asyncmy
        # connections before leaving this loop so they are never reused from a
        # different loop by a later integration test.
        await database_manager.dispose()
