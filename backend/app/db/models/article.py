"""Article ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.article_category import ArticleCategory
    from backend.app.db.models.article_link import ArticleLink
    from backend.app.db.models.chunk import Chunk


class Article(TimestampMixin, Base):
    """Represent a Wikipedia article stored in the database."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    wikipedia_page_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )

    revision_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        LONGTEXT,
        nullable=False,
    )

    word_count: Mapped[int] = mapped_column(
        nullable=False,
    )

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    category_links: Mapped[list[ArticleCategory]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    outgoing_links: Mapped[list[ArticleLink]] = relationship(
        foreign_keys="ArticleLink.source_article_id",
        back_populates="source_article",
        cascade="all, delete-orphan",
    )

    incoming_links: Mapped[list[ArticleLink]] = relationship(
        foreign_keys="ArticleLink.target_article_id",
        back_populates="target_article",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly article representation."""
        return (
            f"Article(id={self.id!r}, "
            f"wikipedia_page_id={self.wikipedia_page_id!r}, "
            f"title={self.title!r})"
        )
