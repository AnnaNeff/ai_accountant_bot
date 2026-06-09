from dataclasses import dataclass
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.schemas.tax_summary import TaxSummary
from app.services.tax_summary_service import (
    TaxSummaryFinancialProfileNotFoundError,
    get_tax_summary,
)
from app.services.user_service import get_or_create_user

router = Router(name="tax_summary")

TAX_SUMMARY_USAGE = "Use format: /tax_summary 2026-05-01 2026-06-30"


@dataclass(frozen=True)
class TaxSummaryCommand:
    period_start: date
    period_end: date


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_tax_summary_command(text: str | None) -> TaxSummaryCommand | str:
    parts = (text or "").split()
    if len(parts) != 3:
        return TAX_SUMMARY_USAGE

    try:
        period_start = date.fromisoformat(parts[1])
        period_end = date.fromisoformat(parts[2])
    except ValueError:
        return TAX_SUMMARY_USAGE

    if period_end < period_start:
        return "Period end must be after period start."
    return TaxSummaryCommand(period_start=period_start, period_end=period_end)


def format_tax_summary(summary: TaxSummary) -> str:
    rows = [
        "Tax summary:",
        "",
        f"Period: {summary.period_start.isoformat()}..{summary.period_end.isoformat()}",
        f"Business type: {summary.business_type}",
        "",
        f"VAT payable estimate: {summary.vat_payable:,.2f} {summary.currency}",
        f"Income tax reserve: {summary.income_tax_reserve:,.2f} {summary.currency}",
        (
            "Bituach Leumi reserve: "
            f"{summary.bituach_leumi_reserve:,.2f} {summary.currency}"
        ),
        "",
        (
            "Total estimated tax reserve: "
            f"{summary.total_estimated_tax_reserve:,.2f} {summary.currency}"
        ),
    ]
    if summary.notes:
        rows.extend(["", "Notes:", "", *(f"* {note}" for note in summary.notes)])
    return "\n".join(rows)


@router.message(Command("tax_summary"))
async def handle_tax_summary(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_tax_summary_command(message.text)
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
            summary = await get_tax_summary(
                session,
                user_id=user.id,
                period_start=command.period_start,
                period_end=command.period_end,
            )
        except TaxSummaryFinancialProfileNotFoundError:
            await message.answer(
                "Financial profile is not set. Use bootstrap.yaml to load initial data."
            )
            return

    await message.answer(format_tax_summary(summary))
