"""Article link ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.db.models.article import Article


class ArticleLink(Base):
    """Represent a directed link between two Wikipedia articles."""

    __tablename__ = "article_links"

    source_article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    target_article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    source_article: Mapped[Article] = relationship(
        foreign_keys=[source_article_id],
        back_populates="outgoing_links",
    )

    target_article: Mapped[Article] = relationship(
        foreign_keys=[target_article_id],
        back_populates="incoming_links",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly article-link representation."""
        return (
            f"ArticleLink(source_article_id={self.source_article_id!r}, "
            f"target_article_id={self.target_article_id!r})"
        )
