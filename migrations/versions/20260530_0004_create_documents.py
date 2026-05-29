"""create documents table

Revision ID: 20260530_0004
Revises: 20260528_0003
Create Date: 2026-05-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260530_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("telegram_file_id", sa.String(length=255), nullable=False),
        sa.Column("local_path", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="uploaded",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_documents_transaction_id"),
        "documents",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(op.f("ix_documents_file_hash"), "documents", ["file_hash"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_file_hash"), table_name="documents")
    op.drop_index(op.f("ix_documents_transaction_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_user_id"), table_name="documents")
    op.drop_table("documents")
