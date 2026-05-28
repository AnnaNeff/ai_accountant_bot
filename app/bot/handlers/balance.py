from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.schemas.balance import BalanceSummary
from app.services.balance_service import (
    FinancialProfileNotFoundError,
    get_balance_summary,
)
from app.services.user_service import get_or_create_user

router = Router(name="balance")


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def format_balance_summary(summary: BalanceSummary) -> str:
    return (
        "Balance summary:\n\n"
        f"Opening balance: {summary.opening_balance:,.2f} {summary.currency}\n"
        f"Opening balance date: {summary.opening_balance_date.isoformat()}\n\n"
        f"Income total: {summary.income_total:,.2f} {summary.currency}\n"
        f"Expense total: {summary.expense_total:,.2f} {summary.currency}\n\n"
        f"Current balance: {summary.current_balance:,.2f} {summary.currency}\n"
        f"Transactions counted: {summary.transactions_count}"
    )


@router.message(Command("balance"))
async def handle_balance(message: Message) -> None:
    if message.from_user is None:
        return

    session_factory = get_async_session_factory()

    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        try:
            summary = await get_balance_summary(session, user.id)
        except FinancialProfileNotFoundError:
            await message.answer(
                "Financial profile is not set. Use bootstrap.yaml to load initial data."
            )
            return

    await message.answer(format_balance_summary(summary))
