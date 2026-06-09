from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class IncomeTaxReserveSummary(BaseModel):
    business_type: str
    period_start: date
    period_end: date
    currency: str
    income_total: Decimal
    deductible_expense_total: Decimal
    taxable_profit: Decimal
    reserve_percent: Decimal | None
    estimated_income_tax_reserve: Decimal
    transactions_count: int
    included_income_count: int
    included_expense_count: int
    skipped_count: int
    notes: list[str]
