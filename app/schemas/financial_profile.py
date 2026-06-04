from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

BusinessType = Literal["unknown", "osek_patur", "osek_murshe"]


class FinancialProfileCreate(BaseModel):
    opening_balance: Decimal = Decimal("0")
    currency: str = "ILS"
    opening_balance_date: date
    business_type: BusinessType = "unknown"
    tax_country: str = "IL"
    default_vat_rate: Decimal | None = None
    income_tax_reserve_percent: Decimal | None = None
    bituach_leumi_reserve_percent: Decimal | None = None

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Opening balance must be a finite number.")
        return value

    @field_validator(
        "default_vat_rate",
        "income_tax_reserve_percent",
        "bituach_leumi_reserve_percent",
    )
    @classmethod
    def validate_percent(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if not value.is_finite() or value < 0 or value > 1:
            raise ValueError("Percent values must be between 0 and 1.")
        return value


class FinancialProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    opening_balance: Decimal
    currency: str
    opening_balance_date: date
    business_type: BusinessType
    tax_country: str
    default_vat_rate: Decimal | None
    income_tax_reserve_percent: Decimal | None
    bituach_leumi_reserve_percent: Decimal | None
    created_at: datetime
    updated_at: datetime
