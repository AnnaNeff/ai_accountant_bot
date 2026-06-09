from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BituachLeumiReserveSummary(BaseModel):
    business_type: str
    period_start: date
    period_end: date
    currency: str
    income_total: Decimal
    deductible_expense_total: Decimal
    estimated_profit: Decimal
    reserve_percent: Decimal | None
    estimated_bituach_leumi_reserve: Decimal
    transactions_count: int
    included_income_count: int
    included_expense_count: int
    skipped_count: int
    notes: list[str]
