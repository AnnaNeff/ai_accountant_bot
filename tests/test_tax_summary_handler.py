import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import tax_summary
from app.bot.handlers.tax_summary import (
    TAX_SUMMARY_USAGE,
    TaxSummaryCommand,
    format_tax_summary,
    parse_tax_summary_command,
)
from app.schemas.tax_summary import TaxSummary
from app.services.tax_summary_service import (
    PLANNING_DISCLAIMER,
    TaxSummaryFinancialProfileNotFoundError,
)


def make_summary(**overrides: object) -> TaxSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "currency": "ILS",
        "vat_payable": Decimal("1440.00"),
        "income_tax_reserve": Decimal("800.00"),
        "bituach_leumi_reserve": Decimal("960.00"),
        "total_estimated_tax_reserve": Decimal("3200.00"),
        "notes": [PLANNING_DISCLAIMER],
        "vat_applicable": True,
        "income_tax_configured": True,
        "bituach_leumi_configured": True,
    }
    data.update(overrides)
    return TaxSummary(**data)


def test_parse_tax_summary_validates_format() -> None:
    assert parse_tax_summary_command("/tax_summary") == TAX_SUMMARY_USAGE
    assert parse_tax_summary_command("/tax_summary 2026-05-01 invalid") == (
        TAX_SUMMARY_USAGE
    )
    assert parse_tax_summary_command(
        "/tax_summary 2026-05-01 2026-06-30 extra"
    ) == TAX_SUMMARY_USAGE


def test_parse_tax_summary_validates_date_order() -> None:
    assert parse_tax_summary_command(
        "/tax_summary 2026-06-30 2026-05-01"
    ) == "Period end must be after period start."

    assert parse_tax_summary_command(
        "/tax_summary 2026-05-01 2026-06-30"
    ) == TaxSummaryCommand(date(2026, 5, 1), date(2026, 6, 30))


def test_format_tax_summary_contains_values_and_disclaimer() -> None:
    text = format_tax_summary(make_summary())

    assert "Period: 2026-05-01..2026-06-30" in text
    assert "Business type: osek_murshe" in text
    assert "VAT payable estimate: 1,440.00 ILS" in text
    assert "Income tax reserve: 800.00 ILS" in text
    assert "Bituach Leumi reserve: 960.00 ILS" in text
    assert "Total estimated tax reserve: 3,200.00 ILS" in text
    assert f"* {PLANNING_DISCLAIMER}" in text


def test_format_tax_summary_for_osek_patur() -> None:
    note = "VAT report is not applicable for osek_patur profile."
    text = format_tax_summary(
        make_summary(
            business_type="osek_patur",
            vat_payable=Decimal("0.00"),
            total_estimated_tax_reserve=Decimal("1760.00"),
            notes=[note, PLANNING_DISCLAIMER],
            vat_applicable=False,
        )
    )

    assert "Business type: osek_patur" in text
    assert "VAT payable estimate: 0.00 ILS" in text
    assert f"* {note}" in text
    assert f"* {PLANNING_DISCLAIMER}" in text


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


def test_tax_summary_handler_returns_read_only_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/tax_summary 2026-05-01 2026-06-30")
    calls: list[tuple[object, int, date, date]] = []

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_tax_summary(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> TaxSummary:
        calls.append((session, user_id, period_start, period_end))
        return make_summary()

    monkeypatch.setattr(
        tax_summary,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        tax_summary,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(tax_summary, "get_tax_summary", fake_get_tax_summary)

    asyncio.run(
        tax_summary.handle_tax_summary(message)  # type: ignore[arg-type]
    )

    assert len(calls) == 1
    assert calls[0][1:] == (7, date(2026, 5, 1), date(2026, 6, 30))
    assert message.answers == [format_tax_summary(make_summary())]


def test_tax_summary_handler_returns_clear_missing_profile_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/tax_summary 2026-05-01 2026-06-30")

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def missing_profile(*args: object, **kwargs: object) -> TaxSummary:
        raise TaxSummaryFinancialProfileNotFoundError("missing")

    monkeypatch.setattr(
        tax_summary,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        tax_summary,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(tax_summary, "get_tax_summary", missing_profile)

    asyncio.run(
        tax_summary.handle_tax_summary(message)  # type: ignore[arg-type]
    )

    assert message.answers == [
        "Financial profile is not set. Use bootstrap.yaml to load initial data."
    ]
