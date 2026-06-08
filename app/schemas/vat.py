from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class VATReportSummary(BaseModel):
    business_type: str
    period_start: date
    period_end: date
    currency: str
    income_total: Decimal
    expense_total: Decimal
    vat_output: Decimal
    vat_input: Decimal
    vat_payable: Decimal
    transactions_count: int
    included_income_count: int
    included_expense_count: int
    skipped_count: int
    notes: list[str]
