from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    vat_included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vat_relevant: Mapped[bool] = mapped_column(
        Boolean,
        server_default="false",
        nullable=False,
    )
    business_use_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        server_default="100.00",
        nullable=False,
    )
    tax_deductible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tax_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance_impact_type: Mapped[str] = mapped_column(
        String(20),
        server_default="business",
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        server_default="ILS",
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20),
        server_default="manual",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="confirmed",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
