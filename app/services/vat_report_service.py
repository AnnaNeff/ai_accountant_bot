from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.schemas.vat import VATReportSummary
from app.tax.israel.vat import MONEY_QUANTUM, calculate_vat_from_gross

ZERO = Decimal("0.00")
PERCENT_DIVISOR = Decimal("100")


class VATReportFinancialProfileNotFoundError(AppError):
    """Raised when a VAT report cannot be built without a financial profile."""


def _empty_report(
    profile: FinancialProfile,
    period_start: date,
    period_end: date,
    note: str,
) -> VATReportSummary:
    return VATReportSummary(
        business_type=profile.business_type,
        period_start=period_start,
        period_end=period_end,
        currency=profile.currency,
        income_total=ZERO,
        expense_total=ZERO,
        vat_output=ZERO,
        vat_input=ZERO,
        vat_payable=ZERO,
        transactions_count=0,
        included_income_count=0,
        included_expense_count=0,
        skipped_count=0,
        notes=[note],
    )


def _transaction_gross_amount(transaction: Transaction) -> Decimal:
    if transaction.amount_total is not None:
        return transaction.amount_total
    return transaction.amount


def _transaction_vat_amount(transaction: Transaction) -> Decimal | None:
    if transaction.vat_amount is not None:
        return transaction.vat_amount
    if transaction.vat_rate is None:
        return None
    _, vat_amount = calculate_vat_from_gross(
        _transaction_gross_amount(transaction),
        transaction.vat_rate,
    )
    return vat_amount


async def get_vat_report(
    session: AsyncSession,
    user_id: int,
    period_start: date,
    period_end: date,
) -> VATReportSummary:
    profile_result = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        raise VATReportFinancialProfileNotFoundError(
            f"Financial profile for user_id={user_id} was not found."
        )

    if profile.business_type == "osek_patur":
        return _empty_report(
            profile,
            period_start,
            period_end,
            "VAT report is not applicable for osek_patur profile.",
        )

    if profile.business_type == "unknown":
        return _empty_report(
            profile,
            period_start,
            period_end,
            "Business type is unknown. Set business_type in financial profile.",
        )

    transactions_result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.status == "confirmed",
            Transaction.date >= period_start,
            Transaction.date <= period_end,
            Transaction.vat_relevant.is_(True),
            Transaction.balance_impact_type == "business",
            Transaction.type.in_(("income", "expense")),
        )
    )
    transactions = list(transactions_result.scalars().all())

    income_total = ZERO
    expense_total = ZERO
    vat_output = ZERO
    vat_input = ZERO
    included_income_count = 0
    included_expense_count = 0
    skipped_count = 0

    for transaction in transactions:
        if transaction.type == "income":
            vat_amount = _transaction_vat_amount(transaction)
            if vat_amount is None:
                skipped_count += 1
                continue
            income_total += _transaction_gross_amount(transaction)
            vat_output += vat_amount
            included_income_count += 1
            continue

        if transaction.tax_deductible is False:
            expense_total += _transaction_gross_amount(transaction)
            included_expense_count += 1
            continue

        vat_amount = _transaction_vat_amount(transaction)
        if vat_amount is None:
            skipped_count += 1
            continue
        business_use_percent = (
            transaction.business_use_percent
            if transaction.business_use_percent is not None
            else PERCENT_DIVISOR
        )
        effective_vat = (
            vat_amount * business_use_percent / PERCENT_DIVISOR
        ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        expense_total += _transaction_gross_amount(transaction)
        vat_input += effective_vat
        included_expense_count += 1

    income_total = income_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    expense_total = expense_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    vat_output = vat_output.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    vat_input = vat_input.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    return VATReportSummary(
        business_type=profile.business_type,
        period_start=period_start,
        period_end=period_end,
        currency=profile.currency,
        income_total=income_total,
        expense_total=expense_total,
        vat_output=vat_output,
        vat_input=vat_input,
        vat_payable=(vat_output - vat_input).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        ),
        transactions_count=included_income_count + included_expense_count,
        included_income_count=included_income_count,
        included_expense_count=included_expense_count,
        skipped_count=skipped_count,
        notes=[],
    )
