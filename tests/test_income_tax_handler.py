import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import income_tax
from app.bot.handlers.income_tax import (
    INCOME_TAX_RESERVE_USAGE,
    IncomeTaxReserveCommand,
    format_income_tax_reserve,
    parse_income_tax_reserve_command,
)
from app.schemas.income_tax import IncomeTaxReserveSummary
from app.services.income_tax_reserve_service import (
    IncomeTaxReserveFinancialProfileNotFoundError,
)


def make_summary(**overrides: object) -> IncomeTaxReserveSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "deductible_expense_total": Decimal("2000.00"),
        "taxable_profit": Decimal("8000.00"),
        "reserve_percent": Decimal("0.10"),
        "estimated_income_tax_reserve": Decimal("800.00"),
        "transactions_count": 8,
        "included_income_count": 5,
        "included_expense_count": 3,
        "skipped_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return IncomeTaxReserveSummary(**data)


def test_parse_income_tax_reserve_validates_format() -> None:
    assert parse_income_tax_reserve_command("/income_tax_reserve") == (
        INCOME_TAX_RESERVE_USAGE
    )
    assert parse_income_tax_reserve_command(
        "/income_tax_reserve 2026-05-01 invalid"
    ) == INCOME_TAX_RESERVE_USAGE
    assert parse_income_tax_reserve_command(
        "/income_tax_reserve 2026-05-01 2026-06-30 extra"
    ) == INCOME_TAX_RESERVE_USAGE


def test_parse_income_tax_reserve_validates_date_order() -> None:
    assert parse_income_tax_reserve_command(
        "/income_tax_reserve 2026-06-30 2026-05-01"
    ) == "Period end must be after period start."

    command = parse_income_tax_reserve_command(
        "/income_tax_reserve 2026-05-01 2026-06-30"
    )
    assert command == IncomeTaxReserveCommand(
        date(2026, 5, 1),
        date(2026, 6, 30),
    )


def test_format_income_tax_reserve_includes_disclaimer() -> None:
    text = format_income_tax_reserve(make_summary())

    assert "Period: 2026-05-01..2026-06-30" in text
    assert "Income total: 10,000.00 ILS" in text
    assert "Deductible expenses: 2,000.00 ILS" in text
    assert "Taxable profit: 8,000.00 ILS" in text
    assert "Reserve percent: 10.00%" in text
    assert "Estimated income tax reserve: 800.00 ILS" in text
    assert "Transactions counted: 8" in text
    assert (
        "This is an estimate for planning only. It is not an official tax "
        "calculation or tax filing."
    ) in text


def test_format_income_tax_reserve_when_percent_is_missing() -> None:
    assert format_income_tax_reserve(
        make_summary(
            reserve_percent=None,
            estimated_income_tax_reserve=Decimal("0.00"),
        )
    ) == (
        "Income tax reserve percent is not set in financial profile.\n\n"
        "Set income_tax_reserve_percent in bootstrap/profile settings.\n\n"
        "This is for planning only."
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


def test_income_tax_reserve_handler_returns_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/income_tax_reserve 2026-05-01 2026-06-30")
    calls: list[tuple[object, int, date, date]] = []

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_income_tax_reserve(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> IncomeTaxReserveSummary:
        calls.append((session, user_id, period_start, period_end))
        return make_summary()

    monkeypatch.setattr(
        income_tax,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        income_tax,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(
        income_tax,
        "get_income_tax_reserve",
        fake_get_income_tax_reserve,
    )

    asyncio.run(
        income_tax.handle_income_tax_reserve(message)  # type: ignore[arg-type]
    )

    assert len(calls) == 1
    assert calls[0][1:] == (7, date(2026, 5, 1), date(2026, 6, 30))
    assert message.answers == [format_income_tax_reserve(make_summary())]


def test_income_tax_reserve_handler_returns_clear_missing_profile_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/income_tax_reserve 2026-05-01 2026-06-30")

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_income_tax_reserve(
        *args: object,
        **kwargs: object,
    ) -> IncomeTaxReserveSummary:
        raise IncomeTaxReserveFinancialProfileNotFoundError("missing")

    monkeypatch.setattr(
        income_tax,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        income_tax,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(
        income_tax,
        "get_income_tax_reserve",
        fake_get_income_tax_reserve,
    )

    asyncio.run(
        income_tax.handle_income_tax_reserve(message)  # type: ignore[arg-type]
    )

    assert message.answers == [
        "Financial profile is not set. Use bootstrap.yaml to load initial data."
    ]
