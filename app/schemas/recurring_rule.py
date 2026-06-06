from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PaymentBehavior = Literal["auto_pay", "manual_pay", "reserve_only"]
ObligationType = Literal[
    "regular",
    "loan",
    "rent",
    "subscription",
    "vat",
    "income_tax",
    "bituach_leumi",
    "other_tax",
    "other",
]


class RecurringRuleCreate(BaseModel):
    type: Literal["income", "expense"]
    amount: Decimal
    currency: str = "ILS"
    category: str | None = None
    description: str
    frequency: Literal["monthly"]
    day_of_month: int = Field(ge=1, le=31)
    payment_behavior: PaymentBehavior = "auto_pay"
    obligation_type: ObligationType = "regular"
    affects_balance_when_generated: bool = True
    start_date: date
    end_date: date | None = None
    active: bool = True

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Amount must be a positive number.")
        return value


class RecurringRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    type: Literal["income", "expense"]
    amount: Decimal
    currency: str
    category: str | None
    description: str
    frequency: Literal["monthly"]
    day_of_month: int
    payment_behavior: PaymentBehavior
    obligation_type: ObligationType
    affects_balance_when_generated: bool
    start_date: date
    end_date: date | None
    active: bool
    last_generated_for_date: date | None
    created_at: datetime
    updated_at: datetime
