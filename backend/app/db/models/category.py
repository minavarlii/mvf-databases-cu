"""Category ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.article_category import ArticleCategory


class Category(TimestampMixin, Base):
    """Represent a Wikipedia category."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
        index=True,
    )

    article_links: Mapped[list[ArticleCategory]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly category representation."""
        return f"Category(id={self.id!r}, name={self.name!r})"
