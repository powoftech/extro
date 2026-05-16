"""initial download schema

Revision ID: 0001
Revises:
Create Date: 2026-05-15 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

_CURRENT_TIMESTAMP = sa.text("(CURRENT_TIMESTAMP)")

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("ourn", sa.String(length=255), nullable=False),
        sa.Column("isbn", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("latest_last_modified_time", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_books_identifier"), "books", ["identifier"], unique=True)
    op.create_index(
        op.f("ix_books_latest_last_modified_time"),
        "books",
        ["latest_last_modified_time"],
        unique=False,
    )
    op.create_index(op.f("ix_books_ourn"), "books", ["ourn"], unique=True)

    op.create_table(
        "book_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("last_modified_time", sa.String(length=64), nullable=False),
        sa.Column("snapshot_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("completed_files", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("downloaded_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "book_id",
            "last_modified_time",
            name="uq_book_snapshots_book_version",
        ),
    )
    op.create_index(
        op.f("ix_book_snapshots_last_modified_time"),
        "book_snapshots",
        ["last_modified_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_book_snapshots_status"),
        "book_snapshots",
        ["status"],
        unique=False,
    )

    op.create_table(
        "book_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("full_path", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("remote_last_modified_time", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("bytes_downloaded", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=_CURRENT_TIMESTAMP,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["book_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "full_path",
            name="uq_book_files_snapshot_path",
        ),
    )
    op.create_index(
        op.f("ix_book_files_snapshot_id"),
        "book_files",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_book_files_status"),
        "book_files",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_book_files_status"), table_name="book_files")
    op.drop_index(op.f("ix_book_files_snapshot_id"), table_name="book_files")
    op.drop_table("book_files")
    op.drop_index(op.f("ix_book_snapshots_status"), table_name="book_snapshots")
    op.drop_index(
        op.f("ix_book_snapshots_last_modified_time"),
        table_name="book_snapshots",
    )
    op.drop_table("book_snapshots")
    op.drop_index(op.f("ix_books_ourn"), table_name="books")
    op.drop_index(op.f("ix_books_latest_last_modified_time"), table_name="books")
    op.drop_index(op.f("ix_books_identifier"), table_name="books")
    op.drop_table("books")
