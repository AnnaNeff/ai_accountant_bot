"""create obligation payments

Revision ID: 20260606_0009
Revises: 20260606_0008
Create Date: 2026-06-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260606_0009"
down_revision: str | None = "20260606_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "obligation_payments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recurring_rule_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="ILS",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="paid",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["recurring_rule_id"], ["recurring_rules.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(
        op.f("ix_obligation_payments_user_id"),
        "obligation_payments",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_payments_recurring_rule_id"),
        "obligation_payments",
        ["recurring_rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_payments_transaction_id"),
        "obligation_payments",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_payments_period_start"),
        "obligation_payments",
        ["period_start"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_payments_period_end"),
        "obligation_payments",
        ["period_end"],
        unique=False,
    )
    op.create_index(
        op.f("ix_obligation_payments_status"),
        "obligation_payments",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_obligation_payments_status"),
        table_name="obligation_payments",
    )
    op.drop_index(
        op.f("ix_obligation_payments_period_end"),
        table_name="obligation_payments",
    )
    op.drop_index(
        op.f("ix_obligation_payments_period_start"),
        table_name="obligation_payments",
    )
    op.drop_index(
        op.f("ix_obligation_payments_transaction_id"),
        table_name="obligation_payments",
    )
    op.drop_index(
        op.f("ix_obligation_payments_recurring_rule_id"),
        table_name="obligation_payments",
    )
    op.drop_index(
        op.f("ix_obligation_payments_user_id"),
        table_name="obligation_payments",
    )
    op.drop_table("obligation_payments")
