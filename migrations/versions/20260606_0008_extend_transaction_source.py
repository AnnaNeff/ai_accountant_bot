"""extend transaction source

Revision ID: 20260606_0008
Revises: 20260604_0007
Create Date: 2026-06-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260606_0008"
down_revision: str | None = "20260604_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "transactions",
        "source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
        existing_server_default="manual",
    )


def downgrade() -> None:
    op.alter_column(
        "transactions",
        "source",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="manual",
    )
