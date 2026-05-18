"""file content sha256

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-18 00:00:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("book_files") as batch:
        batch.add_column(
            sa.Column("content_sha256", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("book_files") as batch:
        batch.drop_column("content_sha256")
