"""book metadata version schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_books_latest_last_modified_time"), table_name="books")
    with op.batch_alter_table("books") as batch:
        batch.add_column(
            sa.Column(
                "authors",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "publishers",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column("publication_date", sa.String(length=32), nullable=True)
        )
        batch.alter_column(
            "latest_last_modified_time",
            new_column_name="latest_version",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
    op.create_index(
        op.f("ix_books_latest_version"),
        "books",
        ["latest_version"],
        unique=False,
    )

    op.drop_index(
        op.f("ix_book_snapshots_last_modified_time"),
        table_name="book_snapshots",
    )
    with op.batch_alter_table("book_snapshots") as batch:
        batch.drop_constraint("uq_book_snapshots_book_version", type_="unique")
        batch.alter_column(
            "last_modified_time",
            new_column_name="version",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
        batch.create_unique_constraint(
            "uq_book_snapshots_book_version",
            ["book_id", "version"],
        )
    op.create_index(
        op.f("ix_book_snapshots_version"),
        "book_snapshots",
        ["version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_book_snapshots_version"), table_name="book_snapshots")
    with op.batch_alter_table("book_snapshots") as batch:
        batch.drop_constraint("uq_book_snapshots_book_version", type_="unique")
        batch.alter_column(
            "version",
            new_column_name="last_modified_time",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
        batch.create_unique_constraint(
            "uq_book_snapshots_book_version",
            ["book_id", "last_modified_time"],
        )
    op.create_index(
        op.f("ix_book_snapshots_last_modified_time"),
        "book_snapshots",
        ["last_modified_time"],
        unique=False,
    )

    op.drop_index(op.f("ix_books_latest_version"), table_name="books")
    with op.batch_alter_table("books") as batch:
        batch.alter_column(
            "latest_version",
            new_column_name="latest_last_modified_time",
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
        batch.drop_column("publication_date")
        batch.drop_column("publishers")
        batch.drop_column("authors")
    op.create_index(
        op.f("ix_books_latest_last_modified_time"),
        "books",
        ["latest_last_modified_time"],
        unique=False,
    )
