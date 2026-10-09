"""Article-to-category association ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.db.models.article import Article
    from backend.app.db.models.category import Category


class ArticleCategory(Base):
    """Associate an article with a Wikipedia category."""

    __tablename__ = "article_categories"

    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "categories.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    article: Mapped[Article] = relationship(
        back_populates="category_links",
    )

    category: Mapped[Category] = relationship(
        back_populates="article_links",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly association representation."""
        return (
            f"ArticleCategory(article_id={self.article_id!r}, "
            f"category_id={self.category_id!r})"
        )
