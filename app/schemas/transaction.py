from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class TransactionCreate(BaseModel):
    type: Literal["income", "expense"]
    amount: Decimal
    currency: str = "ILS"
    date: date
    category: str | None = None
    description: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Amount must be a positive number.")
        return value


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["income", "expense"]
    amount: Decimal
    currency: str
    date: date
    category: str | None
    description: str | None
    source: str
    status: str
    created_at: datetime
