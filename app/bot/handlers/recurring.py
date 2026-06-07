from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.session import async_session_factory
from app.models.obligation_payment import ObligationPayment
from app.models.recurring_rule import RecurringRule
from app.schemas.obligation_payment import ObligationPaymentCreate
from app.schemas.transaction import TransactionCreate
from app.services.obligation_payment_service import (
    create_obligation_payment,
    find_existing_paid_obligation_payment,
    get_recent_obligation_payments,
)
from app.services.obligation_status_service import (
    ExpectedObligationPeriod,
    get_obligation_statuses,
)
from app.services.recurring_service import (
    generate_recurring_transactions,
    get_active_recurring_rules,
    get_active_non_auto_pay_obligations,
    get_recurring_rule_by_id,
)
from app.services.transaction_service import create_transaction
from app.services.user_service import get_or_create_user

router = Router(name="recurring")

PAY_OBLIGATION_USAGE = (
    "Use format: /pay_obligation 5 1200 "
    "2026-05-01 2026-06-30 VAT payment"
)
TAX_OBLIGATION_TYPES = {"vat", "income_tax", "bituach_leumi", "other_tax"}


@dataclass(frozen=True)
class ObligationPaymentCommand:
    rule_id: int
    amount: Decimal
    period_start: date
    period_end: date
    description: str | None


def parse_pay_obligation_command(
    text: str | None,
) -> ObligationPaymentCommand | str:
    parts = (text or "").split(maxsplit=5)
    if len(parts) < 5:
        return PAY_OBLIGATION_USAGE

    try:
        rule_id = int(parts[1])
        amount = Decimal(parts[2])
        period_start = date.fromisoformat(parts[3])
        period_end = date.fromisoformat(parts[4])
    except (ValueError, InvalidOperation):
        return PAY_OBLIGATION_USAGE

    if (
        rule_id <= 0
        or not amount.is_finite()
        or amount <= 0
        or period_end < period_start
    ):
        return PAY_OBLIGATION_USAGE

    return ObligationPaymentCommand(
        rule_id=rule_id,
        amount=amount,
        period_start=period_start,
        period_end=period_end,
        description=parts[5].strip() if len(parts) == 6 and parts[5].strip() else None,
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


def format_obligation_payments(payments: list[ObligationPayment]) -> str:
    if not payments:
        return "No obligation payments yet."

    rows = ["Obligation payments:", ""]
    for number, payment in enumerate(payments, start=1):
        transaction = (
            f"transaction {payment.transaction_id}"
            if payment.transaction_id is not None
            else "no transaction"
        )
        rows.append(
            f"{number}. {payment.status} | rule {payment.recurring_rule_id} | "
            f"{payment.period_start.isoformat()}..{payment.period_end.isoformat()} | "
            f"{payment.amount:,.2f} {payment.currency} | {transaction}"
        )
    return "\n".join(rows)


def format_obligation_statuses(
    statuses: list[ExpectedObligationPeriod],
) -> str:
    if not statuses:
        return "No obligation periods found."

    rows = ["Obligation status:", ""]
    for number, item in enumerate(statuses, start=1):
        payment_detail = f"{item.amount:,.2f} {item.currency}"
        if item.status == "paid" and item.transaction_id is not None:
            payment_detail += f" | transaction {item.transaction_id}"
        rows.append(
            f"{number}. {item.description} | {item.obligation_type} | "
            f"{item.period_start.isoformat()}..{item.period_end.isoformat()} | "
            f"due {item.due_date.isoformat()} | {item.status} | {payment_detail}"
        )
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


@router.message(Command("obligation_payments"))
async def handle_obligation_payments(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        payments = await get_recent_obligation_payments(
            session,
            user_id=user.id,
            limit=10,
        )

    await message.answer(format_obligation_payments(payments))


@router.message(Command("obligation_status"))
async def handle_obligation_status(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        statuses = await get_obligation_statuses(
            session,
            user_id=user.id,
            today=date.today(),
        )

    await message.answer(format_obligation_statuses(statuses))


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

        existing_payment = await find_existing_paid_obligation_payment(
            session,
            user_id=user.id,
            recurring_rule_id=rule.id,
            period_start=command.period_start,
            period_end=command.period_end,
        )
        if existing_payment is not None:
            await message.answer(
                "Obligation payment for this period already exists. Not created."
            )
            return

        description = command.description or rule.description
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
            commit=False,
        )
        await create_obligation_payment(
            session,
            user_id=user.id,
            data=ObligationPaymentCreate(
                recurring_rule_id=rule.id,
                transaction_id=transaction.id,
                period_start=command.period_start,
                period_end=command.period_end,
                amount=command.amount,
                currency=rule.currency,
                status="paid",
                notes=description,
            ),
        )

    await message.answer(
        "Obligation payment saved.\n\n"
        f"Rule ID: {rule.id}\n"
        f"Type: {rule.obligation_type}\n"
        f"Amount: {transaction.amount:.2f} {transaction.currency}\n"
        f"Transaction ID: {transaction.id}"
    )
