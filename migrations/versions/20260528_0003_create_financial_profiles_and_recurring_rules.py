"""create financial profiles and recurring rules

Revision ID: 20260528_0003
Revises: 20260527_0002
Create Date: 2026-05-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260528_0003"
down_revision: str | None = "20260527_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "opening_balance",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="ILS",
            nullable=False,
        ),
        sa.Column("opening_balance_date", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="ILS",
            nullable=False,
        ),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("last_generated_for_date", sa.Date(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(
        op.f("ix_recurring_rules_user_id"),
        "recurring_rules",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_rules_active"),
        "recurring_rules",
        ["active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_rules_day_of_month"),
        "recurring_rules",
        ["day_of_month"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_rules_type"),
        "recurring_rules",
        ["type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recurring_rules_type"), table_name="recurring_rules")
    op.drop_index(op.f("ix_recurring_rules_day_of_month"), table_name="recurring_rules")
    op.drop_index(op.f("ix_recurring_rules_active"), table_name="recurring_rules")
    op.drop_index(op.f("ix_recurring_rules_user_id"), table_name="recurring_rules")
    op.drop_table("recurring_rules")
    op.drop_table("financial_profiles")
