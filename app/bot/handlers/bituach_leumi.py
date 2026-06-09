from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.schemas.bituach_leumi import BituachLeumiReserveSummary
from app.services.bituach_leumi_reserve_service import (
    BituachLeumiReserveFinancialProfileNotFoundError,
    get_bituach_leumi_reserve,
)
from app.services.user_service import get_or_create_user

router = Router(name="bituach_leumi")

BITUACH_LEUMI_RESERVE_USAGE = (
    "Use format: /bituach_leumi_reserve 2026-05-01 2026-06-30"
)


@dataclass(frozen=True)
class BituachLeumiReserveCommand:
    period_start: date
    period_end: date


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_bituach_leumi_reserve_command(
    text: str | None,
) -> BituachLeumiReserveCommand | str:
    parts = (text or "").split()
    if len(parts) != 3:
        return BITUACH_LEUMI_RESERVE_USAGE

    try:
        period_start = date.fromisoformat(parts[1])
        period_end = date.fromisoformat(parts[2])
    except ValueError:
        return BITUACH_LEUMI_RESERVE_USAGE

    if period_end < period_start:
        return "Period end must be after period start."
    return BituachLeumiReserveCommand(
        period_start=period_start,
        period_end=period_end,
    )


def _format_reserve_percent(value: Decimal) -> str:
    return f"{value * Decimal('100'):.2f}%"


def format_bituach_leumi_reserve(summary: BituachLeumiReserveSummary) -> str:
    if summary.reserve_percent is None:
        return (
            "Bituach Leumi reserve percent is not set in financial profile.\n\n"
            "Set bituach_leumi_reserve_percent in bootstrap/profile settings.\n\n"
            "This is for planning only."
        )

    rows = [
        "Bituach Leumi reserve:",
        "",
        f"Period: {summary.period_start.isoformat()}..{summary.period_end.isoformat()}",
        f"Business type: {summary.business_type}",
        "",
        f"Income total: {summary.income_total:,.2f} {summary.currency}",
        (
            "Deductible expenses: "
            f"{summary.deductible_expense_total:,.2f} {summary.currency}"
        ),
        f"Estimated profit: {summary.estimated_profit:,.2f} {summary.currency}",
        "",
        f"Reserve percent: {_format_reserve_percent(summary.reserve_percent)}",
        (
            "Estimated Bituach Leumi reserve: "
            f"{summary.estimated_bituach_leumi_reserve:,.2f} {summary.currency}"
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
                "Bituach Leumi calculation or filing."
            ),
        ]
    )
    return "\n".join(rows)


@router.message(Command("bituach_leumi_reserve"))
async def handle_bituach_leumi_reserve(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_bituach_leumi_reserve_command(message.text)
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
            summary = await get_bituach_leumi_reserve(
                session,
                user_id=user.id,
                period_start=command.period_start,
                period_end=command.period_end,
            )
        except BituachLeumiReserveFinancialProfileNotFoundError:
            await message.answer(
                "Financial profile is not set. Use bootstrap.yaml to load initial data."
            )
            return

    await message.answer(format_bituach_leumi_reserve(summary))
