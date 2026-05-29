from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import create_transaction, get_last_transactions
from app.services.user_service import get_or_create_user

router = Router(name="transactions")

TransactionType = Literal["income", "expense"]


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_transaction_command(
    text: str | None,
    transaction_type: TransactionType,
) -> TransactionCreate | str:
    usage = (
        "Use format: /income 1500 consulting payment"
        if transaction_type == "income"
        else "Use format: /expense 86.40 office supplies"
    )
    parts = (text or "").split(maxsplit=2)
    if len(parts) < 2:
        return usage

    try:
        amount = Decimal(parts[1])
    except InvalidOperation:
        return "Amount must be a positive number."

    if not amount.is_finite() or amount <= 0:
        return "Amount must be a positive number."

    return TransactionCreate(
        type=transaction_type,
        amount=amount,
        date=date.today(),
        description=parts[2] if len(parts) == 3 else None,
    )


def format_last_transactions(transactions: list[Transaction]) -> str:
    if not transactions:
        return "No transactions yet."

    rows = ["Last transactions:", ""]
    for number, transaction in enumerate(transactions, start=1):
        description = transaction.description or ""
        rows.append(
            f"{number}. {transaction.date.isoformat()} | {transaction.type} | "
            f"{transaction.amount:,.2f} {transaction.currency} | {description}"
        )
    return "\n".join(rows)


async def save_transaction(
    message: Message,
    transaction_type: TransactionType,
) -> None:
    if message.from_user is None:
        return

    data = parse_transaction_command(message.text, transaction_type)
    if isinstance(data, str):
        await message.answer(data)
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        transaction = await create_transaction(session, user.id, data)

    await message.answer(
        f"Transaction saved: {transaction.type} | "
        f"{transaction.amount:,.2f} {transaction.currency}"
    )


@router.message(Command("income"))
async def handle_income(message: Message) -> None:
    await save_transaction(message, "income")


@router.message(Command("expense"))
async def handle_expense(message: Message) -> None:
    await save_transaction(message, "expense")


@router.message(Command("last"))
async def handle_last(message: Message) -> None:
    if message.from_user is None:
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        transactions = await get_last_transactions(session, user.id, limit=10)

    await message.answer(format_last_transactions(transactions))
