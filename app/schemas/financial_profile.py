from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class FinancialProfileCreate(BaseModel):
    opening_balance: Decimal = Decimal("0")
    currency: str = "ILS"
    opening_balance_date: date

    @field_validator("opening_balance")
    @classmethod
    def validate_opening_balance(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Opening balance must be a finite number.")
        return value


class FinancialProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    opening_balance: Decimal
    currency: str
    opening_balance_date: date
    created_at: datetime
    updated_at: datetime
