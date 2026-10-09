"""Repository for category persistence operations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Category


class CategoryRepository:
    """Provide asynchronous persistence operations for categories."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: Active SQLAlchemy asynchronous session.
        """
        self._session = session

    async def get_by_id(self, category_id: int) -> Category | None:
        """Return a category by its database identifier.

        Args:
            category_id: Internal category identifier.

        Returns:
            Matching category or ``None``.
        """
        return await self._session.get(Category, category_id)

    async def get_by_name(self, name: str) -> Category | None:
        """Return a category by its exact name.

        Args:
            name: Wikipedia category name.

        Returns:
            Matching category or ``None``.
        """
        statement = select(Category).where(Category.name == name)

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    async def list(self) -> Sequence[Category]:
        """Return all categories ordered by name.

        Returns:
            Sequence containing all stored categories.
        """
        statement = select(Category).order_by(Category.name)

        result = await self._session.execute(statement)

        return result.scalars().all()

    async def add(self, category: Category) -> Category:
        """Add a category to the current transaction.

        Args:
            category: Category instance to persist.

        Returns:
            Persisted category.
        """
        self._session.add(category)
        await self._session.flush()

        return category

    async def get_or_create(self, name: str) -> Category:
        """Return an existing category or create a new one.

        Args:
            name: Wikipedia category name.

        Returns:
            Existing or newly created category.
        """
        category = await self.get_by_name(name)

        if category is not None:
            return category

        category = Category(name=name)

        return await self.add(category)
