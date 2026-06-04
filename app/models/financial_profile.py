from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        server_default="0",
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        server_default="ILS",
        nullable=False,
    )
    opening_balance_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_type: Mapped[str] = mapped_column(
        String(20),
        server_default="unknown",
        nullable=False,
    )
    tax_country: Mapped[str] = mapped_column(
        String(2),
        server_default="IL",
        nullable=False,
    )
    default_vat_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    income_tax_reserve_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    bituach_leumi_reserve_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
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
