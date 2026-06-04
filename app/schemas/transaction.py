from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

BalanceImpactType = Literal[
    "business",
    "personal",
    "tax_payment",
    "transfer",
    "reserve_only",
]


class TransactionCreate(BaseModel):
    type: Literal["income", "expense"]
    amount: Decimal
    amount_total: Decimal | None = None
    amount_net: Decimal | None = None
    vat_amount: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_included: bool | None = None
    vat_relevant: bool = False
    business_use_percent: Decimal = Decimal("100.00")
    tax_deductible: bool | None = None
    tax_category: str | None = None
    balance_impact_type: BalanceImpactType = "business"
    currency: str = "ILS"
    date: date
    category: str | None = None
    description: str | None = None

    @field_validator("amount", "amount_total", "amount_net", "vat_amount")
    @classmethod
    def validate_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if not value.is_finite() or value <= 0:
            raise ValueError("Amount must be a positive number.")
        return value

    @field_validator("vat_rate")
    @classmethod
    def validate_vat_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if not value.is_finite() or value < 0 or value > 1:
            raise ValueError("VAT rate must be between 0 and 1.")
        return value

    @field_validator("business_use_percent")
    @classmethod
    def validate_business_use_percent(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0 or value > 100:
            raise ValueError("Business use percent must be between 0 and 100.")
        return value

    @model_validator(mode="after")
    def default_amount_total(self) -> "TransactionCreate":
        if self.amount_total is None:
            self.amount_total = self.amount
        return self


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["income", "expense"]
    amount: Decimal
    amount_total: Decimal | None
    amount_net: Decimal | None
    vat_amount: Decimal | None
    vat_rate: Decimal | None
    vat_included: bool | None
    vat_relevant: bool
    business_use_percent: Decimal
    tax_deductible: bool | None
    tax_category: str | None
    balance_impact_type: BalanceImpactType
    currency: str
    date: date
    category: str | None
    description: str | None
    source: str
    status: str
    created_at: datetime
