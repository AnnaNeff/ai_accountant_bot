from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.session import async_session_factory
from app.models.recurring_rule import RecurringRule
from app.services.recurring_service import (
    generate_recurring_transactions,
    get_active_recurring_rules,
    get_active_non_auto_pay_obligations,
    get_recurring_rule_by_id,
)
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import (
    create_transaction,
    has_similar_obligation_payment_today,
)
from app.services.user_service import get_or_create_user

router = Router(name="recurring")

PAY_OBLIGATION_USAGE = "Use format: /pay_obligation 5 1200 VAT payment"
TAX_OBLIGATION_TYPES = {"vat", "income_tax", "bituach_leumi", "other_tax"}


@dataclass(frozen=True)
class ObligationPaymentCommand:
    rule_id: int
    amount: Decimal
    description: str | None


def parse_pay_obligation_command(
    text: str | None,
) -> ObligationPaymentCommand | str:
    parts = (text or "").split(maxsplit=3)
    if len(parts) < 3:
        return PAY_OBLIGATION_USAGE

    try:
        rule_id = int(parts[1])
        amount = Decimal(parts[2])
    except (ValueError, InvalidOperation):
        return PAY_OBLIGATION_USAGE

    if rule_id <= 0 or not amount.is_finite() or amount <= 0:
        return PAY_OBLIGATION_USAGE

    return ObligationPaymentCommand(
        rule_id=rule_id,
        amount=amount,
        description=parts[3].strip() if len(parts) == 4 and parts[3].strip() else None,
    )


def format_recurring_rules(rules: list[RecurringRule]) -> str:
    if not rules:
        return "No recurring rules yet."

    rows = ["Recurring rules:", ""]
    for number, rule in enumerate(rules, start=1):
        rows.append(
            f"{number}. {rule.type} | {rule.amount:,.2f} {rule.currency} | "
            f"day {rule.day_of_month} | {rule.payment_behavior} | "
            f"{rule.obligation_type} | {rule.description}"
        )
    return "\n".join(rows)


def format_obligations(rules: list[RecurringRule]) -> str:
    if not rules:
        return "No manual or reserve obligations yet."

    rows = ["Obligations:", ""]
    for number, rule in enumerate(rules, start=1):
        rows.append(
            f"{number}. {rule.payment_behavior} | {rule.obligation_type} | "
            f"{rule.amount:,.2f} {rule.currency} | day {rule.day_of_month} | "
            f"{rule.description}"
        )
    return "\n".join(rows)


def format_generation_result(generated_count: int, skipped_count: int) -> str:
    rows = []
    if generated_count == 0:
        rows.append("No recurring transactions to generate.")
    else:
        rows.append(f"Generated recurring transactions: {generated_count}")

    if skipped_count:
        rows.append(f"Skipped non-auto-pay obligations: {skipped_count}")

    return "\n".join(rows)


@router.message(Command("recurring"))
async def handle_recurring(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        rules = await get_active_recurring_rules(session, user.id)

    await message.answer(format_recurring_rules(rules))


@router.message(Command("obligations"))
async def handle_obligations(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        rules = await get_active_non_auto_pay_obligations(session, user.id)

    await message.answer(format_obligations(rules))


@router.message(Command("generate_recurring"))
async def handle_generate_recurring(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        result = await generate_recurring_transactions(session, user.id)

    await message.answer(
        format_generation_result(
            result.generated_count,
            result.skipped_non_auto_pay_count,
        )
    )


@router.message(Command("pay_obligation"))
async def handle_pay_obligation(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_pay_obligation_command(message.text)
    if isinstance(command, str):
        await message.answer(command)
        return

    payment_date = date.today()
    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        rule = await get_recurring_rule_by_id(
            session,
            user_id=user.id,
            rule_id=command.rule_id,
        )
        if rule is None:
            await message.answer("Obligation not found.")
            return
        if rule.payment_behavior == "auto_pay":
            await message.answer(
                "This obligation is auto-pay. "
                "It is handled by /generate_recurring."
            )
            return
        if rule.payment_behavior == "reserve_only":
            await message.answer(
                "This obligation is reserve-only and cannot be paid directly. "
                "Create a manual expense if needed."
            )
            return
        if rule.payment_behavior != "manual_pay":
            await message.answer("Obligation not found.")
            return

        description = command.description or rule.description
        is_duplicate = await has_similar_obligation_payment_today(
            session,
            user_id=user.id,
            amount=command.amount,
            category=rule.category,
            descriptions=(description, rule.description),
            payment_date=payment_date,
        )
        if is_duplicate:
            await message.answer(
                "Similar obligation payment already exists today. Not created."
            )
            return

        transaction = await create_transaction(
            session,
            user_id=user.id,
            data=TransactionCreate(
                type="expense",
                amount=command.amount,
                amount_total=command.amount,
                currency=rule.currency,
                date=payment_date,
                category=rule.category,
                description=description,
                balance_impact_type=(
                    "tax_payment"
                    if rule.obligation_type in TAX_OBLIGATION_TYPES
                    else "business"
                ),
            ),
            source="obligation_manual_payment",
            status="confirmed",
        )

    await message.answer(
        "Obligation payment saved.\n\n"
        f"Rule ID: {rule.id}\n"
        f"Type: {rule.obligation_type}\n"
        f"Amount: {transaction.amount:.2f} {transaction.currency}\n"
        f"Transaction ID: {transaction.id}"
    )
