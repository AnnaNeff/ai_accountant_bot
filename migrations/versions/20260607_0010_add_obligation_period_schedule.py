"""add obligation period schedule

Revision ID: 20260607_0010
Revises: 20260606_0009
Create Date: 2026-06-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260607_0010"
down_revision: str | None = "20260606_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurring_rules",
        sa.Column(
            "period_months",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "recurring_rules",
        sa.Column("due_day", sa.Integer(), nullable=True),
    )
    op.add_column(
        "recurring_rules",
        sa.Column(
            "due_month_offset",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE recurring_rules "
            "SET period_months = 1, "
            "due_day = day_of_month, "
            "due_month_offset = 0"
        )
    )


def downgrade() -> None:
    op.drop_column("recurring_rules", "due_month_offset")
    op.drop_column("recurring_rules", "due_day")
    op.drop_column("recurring_rules", "period_months")
