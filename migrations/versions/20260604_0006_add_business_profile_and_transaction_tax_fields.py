"""add business profile and transaction tax fields

Revision ID: 20260604_0006
Revises: 20260530_0005
Create Date: 2026-06-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260604_0006"
down_revision: str | None = "20260530_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "financial_profiles",
        sa.Column(
            "business_type",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "financial_profiles",
        sa.Column(
            "tax_country",
            sa.String(length=2),
            server_default="IL",
            nullable=False,
        ),
    )
    op.add_column(
        "financial_profiles",
        sa.Column("default_vat_rate", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.add_column(
        "financial_profiles",
        sa.Column(
            "income_tax_reserve_percent",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
        ),
    )
    op.add_column(
        "financial_profiles",
        sa.Column(
            "bituach_leumi_reserve_percent",
            sa.Numeric(precision=5, scale=4),
            nullable=True,
        ),
    )

    op.add_column(
        "transactions",
        sa.Column("amount_total", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("amount_net", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("vat_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=4), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("vat_included", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "vat_relevant",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "business_use_percent",
            sa.Numeric(precision=5, scale=2),
            server_default="100.00",
            nullable=False,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("tax_deductible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("tax_category", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "balance_impact_type",
            sa.String(length=20),
            server_default="business",
            nullable=False,
        ),
    )
    op.execute("UPDATE transactions SET amount_total = amount WHERE amount_total IS NULL")


def downgrade() -> None:
    op.drop_column("transactions", "balance_impact_type")
    op.drop_column("transactions", "tax_category")
    op.drop_column("transactions", "tax_deductible")
    op.drop_column("transactions", "business_use_percent")
    op.drop_column("transactions", "vat_relevant")
    op.drop_column("transactions", "vat_included")
    op.drop_column("transactions", "vat_rate")
    op.drop_column("transactions", "vat_amount")
    op.drop_column("transactions", "amount_net")
    op.drop_column("transactions", "amount_total")
    op.drop_column("financial_profiles", "bituach_leumi_reserve_percent")
    op.drop_column("financial_profiles", "income_tax_reserve_percent")
    op.drop_column("financial_profiles", "default_vat_rate")
    op.drop_column("financial_profiles", "tax_country")
    op.drop_column("financial_profiles", "business_type")
