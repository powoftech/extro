"""SQLAlchemy ORM models and status enumerations for extro."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Status enumerations
# ---------------------------------------------------------------------------


class SnapshotStatus(StrEnum):
    """Lifecycle states for a :class:`BookSnapshot`."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"


class FileStatus(StrEnum):
    """Lifecycle states for a :class:`BookFile`."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# ORM base and models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ourn: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    isbn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latest_last_modified_time: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )

    snapshots: Mapped[list[BookSnapshot]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )


class BookSnapshot(Base):
    __tablename__ = "book_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "last_modified_time",
            name="uq_book_snapshots_book_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    last_modified_time: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        default=SnapshotStatus.PENDING,
        index=True,
    )
    total_files: Mapped[int] = mapped_column(default=0)
    completed_files: Mapped[int] = mapped_column(default=0)
    total_bytes: Mapped[int] = mapped_column(default=0)
    downloaded_bytes: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )

    book: Mapped[Book] = relationship(back_populates="snapshots")
    files: Mapped[list[BookFile]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class BookFile(Base):
    __tablename__ = "book_files"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "full_path",
            name="uq_book_files_snapshot_path",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"),
        index=True,
    )
    url: Mapped[str] = mapped_column(Text)
    full_path: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    remote_last_modified_time: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=FileStatus.PENDING,
        index=True,
    )
    bytes_downloaded: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )

    snapshot: Mapped[BookSnapshot] = relationship(back_populates="files")
