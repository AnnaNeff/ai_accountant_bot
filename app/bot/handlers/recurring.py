from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.session import async_session_factory
from app.models.recurring_rule import RecurringRule
from app.services.recurring_service import (
    generate_recurring_transactions,
    get_active_recurring_rules,
)
from app.services.user_service import get_or_create_user

router = Router(name="recurring")


def format_recurring_rules(rules: list[RecurringRule]) -> str:
    if not rules:
        return "No recurring rules yet."

    rows = ["Recurring rules:", ""]
    for number, rule in enumerate(rules, start=1):
        rows.append(
            f"{number}. {rule.type} | {rule.amount:,.2f} {rule.currency} | "
            f"day {rule.day_of_month} | {rule.description}"
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
        generated_count = await generate_recurring_transactions(session, user.id)

    if generated_count == 0:
        await message.answer("No recurring transactions to generate.")
        return

    await message.answer(f"Generated recurring transactions: {generated_count}")
