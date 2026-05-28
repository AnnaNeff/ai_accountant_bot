from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.schemas.balance import BalanceSummary


class FinancialProfileNotFoundError(AppError):
    """Raised when balance cannot be calculated without a financial profile."""


async def get_balance_summary(
    session: AsyncSession,
    user_id: int,
) -> BalanceSummary:
    profile_result = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile is None:
        raise FinancialProfileNotFoundError(
            f"Financial profile for user_id={user_id} was not found."
        )

    transactions_result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.status == "confirmed",
        )
    )
    transactions = list(transactions_result.scalars().all())

    income_total = sum(
        (
            transaction.amount
            for transaction in transactions
            if transaction.type == "income"
        ),
        Decimal("0"),
    )
    expense_total = sum(
        (
            transaction.amount
            for transaction in transactions
            if transaction.type == "expense"
        ),
        Decimal("0"),
    )

    return BalanceSummary(
        opening_balance=profile.opening_balance,
        currency=profile.currency,
        opening_balance_date=profile.opening_balance_date,
        income_total=income_total,
        expense_total=expense_total,
        current_balance=profile.opening_balance + income_total - expense_total,
        transactions_count=len(transactions),
    )
