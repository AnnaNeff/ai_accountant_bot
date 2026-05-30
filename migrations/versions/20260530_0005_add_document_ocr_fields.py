"""add document OCR fields

Revision ID: 20260530_0005
Revises: 20260530_0004
Create Date: 2026-05-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260530_0005"
down_revision: str | None = "20260530_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "ocr_status",
            sa.String(length=20),
            server_default="not_started",
            nullable=False,
        ),
    )
    op.add_column("documents", sa.Column("ocr_error", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("ocr_processed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "ocr_processed_at")
    op.drop_column("documents", "ocr_error")
    op.drop_column("documents", "ocr_status")
    op.drop_column("documents", "ocr_text")
