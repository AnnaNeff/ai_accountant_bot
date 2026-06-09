from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.schemas.bituach_leumi import BituachLeumiReserveSummary

MONEY_QUANTUM = Decimal("0.01")
PERCENT_DIVISOR = Decimal("100")
ZERO = Decimal("0.00")


class BituachLeumiReserveFinancialProfileNotFoundError(AppError):
    """Raised when a Bituach Leumi reserve requires a financial profile."""


def _empty_summary(
    profile: FinancialProfile,
    period_start: date,
    period_end: date,
    note: str,
) -> BituachLeumiReserveSummary:
    return BituachLeumiReserveSummary(
        business_type=profile.business_type,
        period_start=period_start,
        period_end=period_end,
        currency=profile.currency,
        income_total=ZERO,
        deductible_expense_total=ZERO,
        estimated_profit=ZERO,
        reserve_percent=profile.bituach_leumi_reserve_percent,
        estimated_bituach_leumi_reserve=ZERO,
        transactions_count=0,
        included_income_count=0,
        included_expense_count=0,
        skipped_count=0,
        notes=[note],
    )


def _estimated_amount(transaction: Transaction) -> Decimal:
    if transaction.amount_net is not None:
        return transaction.amount_net
    if transaction.amount_total is not None and transaction.vat_amount is not None:
        return transaction.amount_total - transaction.vat_amount
    if transaction.amount_total is not None:
        return transaction.amount_total
    return transaction.amount


async def get_bituach_leumi_reserve(
    session: AsyncSession,
    user_id: int,
    period_start: date,
    period_end: date,
) -> BituachLeumiReserveSummary:
    profile_result = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        raise BituachLeumiReserveFinancialProfileNotFoundError(
            f"Financial profile for user_id={user_id} was not found."
        )

    if profile.bituach_leumi_reserve_percent is None:
        return _empty_summary(
            profile,
            period_start,
            period_end,
            "Bituach Leumi reserve percent is not set in financial profile.",
        )

    transactions_result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.status == "confirmed",
            Transaction.date >= period_start,
            Transaction.date <= period_end,
            Transaction.balance_impact_type == "business",
            Transaction.type.in_(("income", "expense")),
        )
    )
    transactions = list(transactions_result.scalars().all())

    income_total = ZERO
    deductible_expense_total = ZERO
    included_income_count = 0
    included_expense_count = 0
    skipped_count = 0

    for transaction in transactions:
        estimated_amount = _estimated_amount(transaction)

        if transaction.type == "income":
            income_total += estimated_amount
            included_income_count += 1
            continue

        included_expense_count += 1
        if transaction.tax_deductible is False:
            continue

        business_use_percent = (
            transaction.business_use_percent
            if transaction.business_use_percent is not None
            else PERCENT_DIVISOR
        )
        effective_expense = (
            estimated_amount * business_use_percent / PERCENT_DIVISOR
        ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        deductible_expense_total += effective_expense

    income_total = income_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    deductible_expense_total = deductible_expense_total.quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    estimated_profit = (income_total - deductible_expense_total).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    notes: list[str] = []
    if profile.business_type == "unknown":
        notes.append(
            "Business type is unknown. Reserve is based only on configured "
            "bituach_leumi_reserve_percent."
        )

    if estimated_profit <= ZERO:
        estimated_reserve = ZERO
        notes.append("No positive estimated profit for this period.")
    else:
        estimated_reserve = (
            estimated_profit * profile.bituach_leumi_reserve_percent
        ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    return BituachLeumiReserveSummary(
        business_type=profile.business_type,
        period_start=period_start,
        period_end=period_end,
        currency=profile.currency,
        income_total=income_total,
        deductible_expense_total=deductible_expense_total,
        estimated_profit=estimated_profit,
        reserve_percent=profile.bituach_leumi_reserve_percent,
        estimated_bituach_leumi_reserve=estimated_reserve,
        transactions_count=included_income_count + included_expense_count,
        included_income_count=included_income_count,
        included_expense_count=included_expense_count,
        skipped_count=skipped_count,
        notes=notes,
    )
