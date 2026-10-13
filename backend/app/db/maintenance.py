"""Database maintenance helpers."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ANALYZE_CORE_TABLES_SQL = """
ANALYZE TABLE
    articles,
    chunks,
    article_categories,
    categories,
    article_links
"""


async def analyze_core_tables(
    session: AsyncSession,
) -> None:
    """Refresh MariaDB optimizer statistics for MVF tables."""
    await session.execute(text(ANALYZE_CORE_TABLES_SQL))
