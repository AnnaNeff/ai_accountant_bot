import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import vat
from app.bot.handlers.vat import (
    VAT_REPORT_USAGE,
    VATReportCommand,
    format_vat_report,
    parse_vat_report_command,
)
from app.schemas.vat import VATReportSummary
from app.services.vat_report_service import VATReportFinancialProfileNotFoundError


def make_summary(**overrides: object) -> VATReportSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "expense_total": Decimal("2000.00"),
        "vat_output": Decimal("1800.00"),
        "vat_input": Decimal("360.00"),
        "vat_payable": Decimal("1440.00"),
        "transactions_count": 8,
        "included_income_count": 5,
        "included_expense_count": 3,
        "skipped_count": 1,
        "notes": [],
    }
    data.update(overrides)
    return VATReportSummary(**data)


def test_parse_vat_report_validates_format() -> None:
    assert parse_vat_report_command("/vat_report") == VAT_REPORT_USAGE
    assert parse_vat_report_command("/vat_report 2026-05-01 invalid") == (
        VAT_REPORT_USAGE
    )
    assert parse_vat_report_command("/vat_report 2026-05-01 2026-06-30 extra") == (
        VAT_REPORT_USAGE
    )


def test_parse_vat_report_validates_date_order() -> None:
    assert parse_vat_report_command("/vat_report 2026-06-30 2026-05-01") == (
        "Period end must be after period start."
    )

    command = parse_vat_report_command("/vat_report 2026-05-01 2026-06-30")
    assert command == VATReportCommand(date(2026, 5, 1), date(2026, 6, 30))


def test_format_vat_report_includes_planning_only_disclaimer() -> None:
    text = format_vat_report(make_summary())

    assert "Period: 2026-05-01..2026-06-30" in text
    assert "Income total: 10,000.00 ILS" in text
    assert "Estimated VAT payable: 1,440.00 ILS" in text
    assert "Transactions counted: 8" in text
    assert "Skipped transactions: 1" in text
    assert (
        "This is an estimate for planning only. It is not an official tax filing."
        in text
    )


def test_format_vat_report_for_osek_patur() -> None:
    text = format_vat_report(
        make_summary(
            business_type="osek_patur",
            notes=["VAT report is not applicable for osek_patur profile."],
        )
    )

    assert text == (
        "VAT report:\n\n"
        "Business type: osek_patur\n\n"
        "VAT report is not applicable for osek_patur profile.\n\n"
        "This is for planning only. Confirm tax treatment with your accountant."
    )


def test_format_vat_report_for_unknown_business_type() -> None:
    assert format_vat_report(make_summary(business_type="unknown")) == (
        "Business type is unknown. Set business_type in financial profile."
    )


class FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=123, full_name="Test User")
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def test_vat_report_handler_returns_report_without_creating_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/vat_report 2026-05-01 2026-06-30")
    calls: list[tuple[object, int, date, date]] = []

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_vat_report(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> VATReportSummary:
        calls.append((session, user_id, period_start, period_end))
        return make_summary()

    monkeypatch.setattr(vat, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(vat, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(vat, "get_vat_report", fake_get_vat_report)

    asyncio.run(vat.handle_vat_report(message))  # type: ignore[arg-type]

    assert len(calls) == 1
    assert calls[0][1:] == (7, date(2026, 5, 1), date(2026, 6, 30))
    assert message.answers == [format_vat_report(make_summary())]


def test_vat_report_handler_returns_clear_error_when_profile_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/vat_report 2026-05-01 2026-06-30")

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_vat_report(*args: object, **kwargs: object) -> VATReportSummary:
        raise VATReportFinancialProfileNotFoundError("missing")

    monkeypatch.setattr(vat, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(vat, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(vat, "get_vat_report", fake_get_vat_report)

    asyncio.run(vat.handle_vat_report(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Financial profile is not set. Use bootstrap.yaml to load initial data."
    ]
