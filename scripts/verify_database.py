"""Verify the MVF MariaDB configuration and database schema."""

import asyncio

from sqlalchemy import text

from backend.app.db import database_manager


class DatabaseVerifier:
    """Verify MariaDB connectivity and required database features."""

    async def verify(self) -> None:
        """Run all database verification checks."""
        async with database_manager.session() as session:
            version = await session.scalar(text("SELECT VERSION()"))

            tables = await session.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    ORDER BY table_name
                    """
                )
            )

            table_names = list(tables.scalars())

            vector_type = await session.scalar(
                text(
                    """
                    SELECT column_type
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = 'chunks'
                      AND column_name = 'embedding'
                    """
                )
            )

        print(f"MariaDB version: {version}")
        print(f"Tables: {', '.join(table_names)}")
        print(f"Chunk embedding type: {vector_type}")

        await database_manager.dispose()


async def main() -> None:
    """Run the database verification script."""
    verifier = DatabaseVerifier()
    await verifier.verify()


if __name__ == "__main__":
    asyncio.run(main())
