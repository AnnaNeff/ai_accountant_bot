from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class BalanceSummary(BaseModel):
    opening_balance: Decimal
    currency: str
    opening_balance_date: date
    income_total: Decimal
    expense_total: Decimal
    current_balance: Decimal
    transactions_count: int
