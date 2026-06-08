from dataclasses import dataclass
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.schemas.vat import VATReportSummary
from app.services.user_service import get_or_create_user
from app.services.vat_report_service import (
    VATReportFinancialProfileNotFoundError,
    get_vat_report,
)

router = Router(name="vat")

VAT_REPORT_USAGE = "Use format: /vat_report 2026-05-01 2026-06-30"


@dataclass(frozen=True)
class VATReportCommand:
    period_start: date
    period_end: date


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_vat_report_command(text: str | None) -> VATReportCommand | str:
    parts = (text or "").split()
    if len(parts) != 3:
        return VAT_REPORT_USAGE

    try:
        period_start = date.fromisoformat(parts[1])
        period_end = date.fromisoformat(parts[2])
    except ValueError:
        return VAT_REPORT_USAGE

    if period_end < period_start:
        return "Period end must be after period start."
    return VATReportCommand(period_start=period_start, period_end=period_end)


def format_vat_report(summary: VATReportSummary) -> str:
    if summary.business_type == "unknown":
        return "Business type is unknown. Set business_type in financial profile."

    if summary.business_type == "osek_patur":
        return (
            "VAT report:\n\n"
            "Business type: osek_patur\n\n"
            "VAT report is not applicable for osek_patur profile.\n\n"
            "This is for planning only. Confirm tax treatment with your accountant."
        )

    return (
        "VAT report:\n\n"
        f"Period: {summary.period_start.isoformat()}..{summary.period_end.isoformat()}\n"
        f"Business type: {summary.business_type}\n\n"
        f"Income total: {summary.income_total:,.2f} {summary.currency}\n"
        f"Expense total: {summary.expense_total:,.2f} {summary.currency}\n\n"
        f"VAT output: {summary.vat_output:,.2f} {summary.currency}\n"
        f"VAT input: {summary.vat_input:,.2f} {summary.currency}\n\n"
        f"Estimated VAT payable: {summary.vat_payable:,.2f} {summary.currency}\n\n"
        f"Transactions counted: {summary.transactions_count}\n"
        f"Skipped transactions: {summary.skipped_count}\n\n"
        "This is an estimate for planning only. It is not an official tax filing."
    )


@router.message(Command("vat_report"))
async def handle_vat_report(message: Message) -> None:
    if message.from_user is None:
        return

    command = parse_vat_report_command(message.text)
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
            summary = await get_vat_report(
                session,
                user_id=user.id,
                period_start=command.period_start,
                period_end=command.period_end,
            )
        except VATReportFinancialProfileNotFoundError:
            await message.answer(
                "Financial profile is not set. Use bootstrap.yaml to load initial data."
            )
            return

    await message.answer(format_vat_report(summary))
