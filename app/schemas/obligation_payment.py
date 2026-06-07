from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ObligationPaymentCreate(BaseModel):
    recurring_rule_id: int
    transaction_id: int | None = None
    period_start: date
    period_end: date
    amount: Decimal
    currency: str = "ILS"
    status: Literal["paid", "cancelled"] = "paid"
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Amount must be a positive number.")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> "ObligationPaymentCreate":
        if self.period_end < self.period_start:
            raise ValueError("Period end must be on or after period start.")
        return self


class ObligationPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    recurring_rule_id: int
    transaction_id: int | None
    period_start: date
    period_end: date
    amount: Decimal
    currency: str
    status: Literal["paid", "cancelled"]
    notes: str | None
    created_at: datetime
    updated_at: datetime
