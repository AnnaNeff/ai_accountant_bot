from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class TaxSummary(BaseModel):
    business_type: str
    period_start: date
    period_end: date
    currency: str
    vat_payable: Decimal
    income_tax_reserve: Decimal
    bituach_leumi_reserve: Decimal
    total_estimated_tax_reserve: Decimal
    notes: list[str]
    vat_applicable: bool
    income_tax_configured: bool
    bituach_leumi_configured: bool
