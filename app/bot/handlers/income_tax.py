from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.schemas.income_tax import IncomeTaxReserveSummary
from app.services.income_tax_reserve_service import (
    IncomeTaxReserveFinancialProfileNotFoundError,
    get_income_tax_reserve,
)
from app.services.user_service import get_or_create_user

router = Router(name="income_tax")

INCOME_TAX_RESERVE_USAGE = (
    "Use format: /income_tax_reserve 2026-05-01 2026-06-30"
)


@dataclass(frozen=True)
class IncomeTaxReserveCommand:
    period_start: date
    period_end: date


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_income_tax_reserve_command(
    text: str | None,
) -> IncomeTaxReserveCommand | str:
    parts = (text or "").split()
    if len(parts) != 3:
        return INCOME_TAX_RESERVE_USAGE

    try:
        period_start = date.fromisoformat(parts[1])
        period_end = date.fromisoformat(parts[2])
    except ValueError:
        return INCOME_TAX_RESERVE_USAGE

    if period_end < period_start:
        return "Period end must be after period start."
    return IncomeTaxReserveCommand(
        period_start=period_start,
        period_end=period_end,
    )


def _format_reserve_percent(value: Decimal) -> str:
    return f"{value * Decimal('100'):.2f}%"


def format_income_tax_reserve(summary: IncomeTaxReserveSummary) -> str:
    if summary.reserve_percent is None:
        return (
            "Income tax reserve percent is not set in financial profile.\n\n"
            "Set income_tax_reserve_percent in bootstrap/profile settings.\n\n"
            "This is for planning only."
        )

    rows = [
        "Income tax reserve:",
        "",
        f"Period: {summary.period_start.isoformat()}..{summary.period_end.isoformat()}",
        f"Business type: {summary.business_type}",
        "",
        f"Income total: {summary.income_total:,.2f} {summary.currency}",
        (
            "Deductible expenses: "
            f"{summary.deductible_expense_total:,.2f} {summary.currency}"
        ),
        f"Taxable profit: {summary.taxable_profit:,.2f} {summary.currency}",
        "",
        f"Reserve percent: {_format_reserve_percent(summary.reserve_percent)}",
        (
            "Estimated income tax reserve: "
            f"{summary.estimated_income_tax_reserve:,.2f} {summary.currency}"
        ),
        "",
        f"Transactions counted: {summary.transactions_count}",
        f"Skipped transactions: {summary.skipped_count}",
    ]
    if summary.notes:
        rows.extend(["", *summary.notes])
    rows.extend(
        [
            "",
            (
                "This is an estimate for planning only. It is not an official "
                "tax calculation or tax filing."
            ),
        ]
    )
    return "\n".join(rows)


@router.message(Command("income_tax_reserve"))
async def handle_income_tax_reserve(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_income_tax_reserve_command(message.text)
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
        try:
            summary = await get_income_tax_reserve(
                session,
                user_id=user.id,
                period_start=command.period_start,
                period_end=command.period_end,
            )
        except IncomeTaxReserveFinancialProfileNotFoundError:
            await message.answer(
                "Financial profile is not set. Use bootstrap.yaml to load initial data."
            )
            return

    await message.answer(format_income_tax_reserve(summary))
