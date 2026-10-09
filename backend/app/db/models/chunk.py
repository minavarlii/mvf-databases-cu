"""Article chunk ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.models.mixins import TimestampMixin
from backend.app.db.types import MariaDBVector

if TYPE_CHECKING:
    from backend.app.db.models.article import Article


class Chunk(TimestampMixin, Base):
    """Represent a text chunk and its semantic embedding."""

    __tablename__ = "chunks"

    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "chunk_index",
            name="uq_chunks_article_chunk_index",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    embedding: Mapped[bytes] = mapped_column(
        MariaDBVector(384),
        nullable=False,
    )

    article: Mapped[Article] = relationship(
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        """Return a developer-friendly chunk representation."""
        return (
            f"Chunk(id={self.id!r}, "
            f"article_id={self.article_id!r}, "
            f"chunk_index={self.chunk_index!r})"
        )
