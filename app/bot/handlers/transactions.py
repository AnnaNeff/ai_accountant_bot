from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import (
    BALANCE_IMPACT_TYPES,
    BOOLEAN_TRANSACTION_TAX_FIELDS,
    DECIMAL_TRANSACTION_TAX_FIELD_RANGES,
    UPDATABLE_TRANSACTION_TAX_FIELDS,
    create_transaction,
    get_last_transactions,
    get_transaction_by_id,
    update_transaction_tax_field,
)
from app.services.user_service import get_or_create_user

router = Router(name="transactions")

TransactionType = Literal["income", "expense"]
TRANSACTION_USAGE = "Use format: /transaction 123"
SET_TRANSACTION_TAX_USAGE = (
    "Use format: /set_transaction_tax 123 vat_relevant true"
)
SUPPORTED_TAX_FIELDS = UPDATABLE_TRANSACTION_TAX_FIELDS


@dataclass(frozen=True)
class TransactionTaxUpdateCommand:
    transaction_id: int
    field: str
    value: Any
    display_value: str


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


def parse_transaction_id_command(text: str | None) -> int | str:
    parts = (text or "").split()
    if len(parts) != 2:
        return TRANSACTION_USAGE

    try:
        transaction_id = int(parts[1])
    except ValueError:
        return TRANSACTION_USAGE

    if transaction_id <= 0:
        return TRANSACTION_USAGE
    return transaction_id


def parse_boolean(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    return None


def parse_set_transaction_tax_command(
    text: str | None,
) -> TransactionTaxUpdateCommand | str:
    parts = (text or "").split()
    if len(parts) != 4:
        return SET_TRANSACTION_TAX_USAGE

    try:
        transaction_id = int(parts[1])
    except ValueError:
        return SET_TRANSACTION_TAX_USAGE
    if transaction_id <= 0:
        return SET_TRANSACTION_TAX_USAGE

    field = parts[2]
    raw_value = parts[3]
    if field not in SUPPORTED_TAX_FIELDS:
        return "Unsupported tax field."

    if field in DECIMAL_TRANSACTION_TAX_FIELD_RANGES:
        try:
            value = Decimal(raw_value)
        except InvalidOperation:
            return "Invalid value for this field."
        minimum, maximum = DECIMAL_TRANSACTION_TAX_FIELD_RANGES[field]
        if (
            not value.is_finite()
            or value < minimum
            or maximum is not None
            and value > maximum
        ):
            return "Invalid value for this field."
        display_value = str(value)
    elif field in BOOLEAN_TRANSACTION_TAX_FIELDS:
        value = parse_boolean(raw_value)
        if value is None:
            return "Invalid value for this field."
        display_value = "true" if value else "false"
    elif field == "balance_impact_type":
        if raw_value not in BALANCE_IMPACT_TYPES:
            return "Invalid value for this field."
        value = raw_value
        display_value = raw_value
    else:
        value = None if raw_value.casefold() == "null" else raw_value
        if value is not None and len(value) > 255:
            return "Invalid value for this field."
        display_value = "null" if value is None else raw_value

    return TransactionTaxUpdateCommand(
        transaction_id=transaction_id,
        field=field,
        value=value,
        display_value=display_value,
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


def format_optional_decimal(value: Decimal | None) -> str:
    return f"{value:.2f}" if value is not None else "not set"


def format_optional_boolean(value: bool | None) -> str:
    if value is None:
        return "not set"
    return "yes" if value else "no"


def format_transaction_details(transaction: Transaction) -> str:
    return (
        "Transaction details:\n\n"
        f"ID: {transaction.id}\n"
        f"Date: {transaction.date.isoformat()}\n"
        f"Type: {transaction.type}\n"
        f"Amount: {transaction.amount:.2f} {transaction.currency}\n"
        f"Description: {transaction.description or 'not set'}\n"
        f"Category: {transaction.category or 'not set'}\n"
        f"Source: {transaction.source}\n"
        f"Status: {transaction.status}\n\n"
        "Tax/business fields:\n"
        f"Amount total: {format_optional_decimal(transaction.amount_total)}\n"
        f"Amount net: {format_optional_decimal(transaction.amount_net)}\n"
        f"VAT amount: {format_optional_decimal(transaction.vat_amount)}\n"
        f"VAT rate: "
        f"{str(transaction.vat_rate) if transaction.vat_rate is not None else 'not set'}\n"
        f"VAT included: {format_optional_boolean(transaction.vat_included)}\n"
        f"VAT relevant: {'yes' if transaction.vat_relevant else 'no'}\n"
        f"Business use: {transaction.business_use_percent:.2f}%\n"
        f"Tax deductible: {format_optional_boolean(transaction.tax_deductible)}\n"
        f"Tax category: {transaction.tax_category or 'not set'}\n"
        f"Balance impact type: {transaction.balance_impact_type}"
    )


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


@router.message(Command("transaction"))
async def handle_transaction(message: Message) -> None:
    if message.from_user is None:
        return

    transaction_id = parse_transaction_id_command(message.text)
    if isinstance(transaction_id, str):
        await message.answer(transaction_id)
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        transaction = await get_transaction_by_id(
            session,
            user_id=user.id,
            transaction_id=transaction_id,
        )

    if transaction is None:
        await message.answer("Transaction not found.")
        return
    await message.answer(format_transaction_details(transaction))


@router.message(Command("set_transaction_tax"))
async def handle_set_transaction_tax(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_set_transaction_tax_command(message.text)
    if isinstance(command, str):
        await message.answer(command)
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        transaction = await update_transaction_tax_field(
            session,
            user_id=user.id,
            transaction_id=command.transaction_id,
            field=command.field,
            value=command.value,
        )

    if transaction is None:
        await message.answer("Transaction not found.")
        return
    await message.answer(
        "Transaction tax field updated.\n\n"
        f"Transaction ID: {transaction.id}\n"
        f"Field: {command.field}\n"
        f"Value: {command.display_value}"
    )
