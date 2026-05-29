from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ExtractedTransaction(BaseModel):
    type: Literal["income", "expense", "unknown"]
    amount: Decimal | None = None
    currency: str = "ILS"
    date: Date | None = None
    category: str | None = None
    description: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_confirmation: bool
    raw_text: str

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("Amount must be a positive number.")
        return value
