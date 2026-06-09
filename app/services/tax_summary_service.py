from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.schemas.tax_summary import TaxSummary
from app.services.bituach_leumi_reserve_service import (
    BituachLeumiReserveFinancialProfileNotFoundError,
    get_bituach_leumi_reserve,
)
from app.services.income_tax_reserve_service import (
    IncomeTaxReserveFinancialProfileNotFoundError,
    get_income_tax_reserve,
)
from app.services.vat_report_service import (
    VATReportFinancialProfileNotFoundError,
    get_vat_report,
)

ZERO = Decimal("0.00")
PLANNING_DISCLAIMER = (
    "This is an estimate for planning only. It is not an official tax "
    "calculation, tax filing, or payment instruction."
)


class TaxSummaryFinancialProfileNotFoundError(AppError):
    """Raised when a tax summary cannot be built without a financial profile."""


def _unique_notes(*note_groups: list[str]) -> list[str]:
    notes: list[str] = []
    for note_group in note_groups:
        for note in note_group:
            if note not in notes:
                notes.append(note)
    return notes


async def get_tax_summary(
    session: AsyncSession,
    user_id: int,
    period_start: date,
    period_end: date,
) -> TaxSummary:
    try:
        vat_report = await get_vat_report(
            session,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
        )
        income_tax = await get_income_tax_reserve(
            session,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
        )
        bituach_leumi = await get_bituach_leumi_reserve(
            session,
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
        )
    except (
        VATReportFinancialProfileNotFoundError,
        IncomeTaxReserveFinancialProfileNotFoundError,
        BituachLeumiReserveFinancialProfileNotFoundError,
    ) as exc:
        raise TaxSummaryFinancialProfileNotFoundError(str(exc)) from exc

    vat_payable = (
        vat_report.vat_payable
        if vat_report.business_type == "osek_murshe"
        else ZERO
    )
    income_tax_reserve = income_tax.estimated_income_tax_reserve
    bituach_leumi_reserve = bituach_leumi.estimated_bituach_leumi_reserve
    total_estimated_tax_reserve = (
        max(vat_payable, ZERO)
        + income_tax_reserve
        + bituach_leumi_reserve
    )
    notes = _unique_notes(
        vat_report.notes,
        income_tax.notes,
        bituach_leumi.notes,
        [PLANNING_DISCLAIMER],
    )

    return TaxSummary(
        business_type=vat_report.business_type,
        period_start=period_start,
        period_end=period_end,
        currency=vat_report.currency,
        vat_payable=vat_payable,
        income_tax_reserve=income_tax_reserve,
        bituach_leumi_reserve=bituach_leumi_reserve,
        total_estimated_tax_reserve=total_estimated_tax_reserve,
        notes=notes,
        vat_applicable=vat_report.business_type == "osek_murshe",
        income_tax_configured=income_tax.reserve_percent is not None,
        bituach_leumi_configured=bituach_leumi.reserve_percent is not None,
    )
