"""add recurring obligation fields

Revision ID: 20260604_0007
Revises: 20260604_0006
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260604_0007"
down_revision: str | None = "20260604_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recurring_rules",
        sa.Column(
            "payment_behavior",
            sa.String(length=20),
            server_default="auto_pay",
            nullable=False,
        ),
    )
    op.add_column(
        "recurring_rules",
        sa.Column(
            "obligation_type",
            sa.String(length=20),
            server_default="regular",
            nullable=False,
        ),
    )
    op.add_column(
        "recurring_rules",
        sa.Column(
            "affects_balance_when_generated",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("recurring_rules", "affects_balance_when_generated")
    op.drop_column("recurring_rules", "obligation_type")
    op.drop_column("recurring_rules", "payment_behavior")
