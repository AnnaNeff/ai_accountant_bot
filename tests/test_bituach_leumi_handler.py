import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import bituach_leumi
from app.bot.handlers.bituach_leumi import (
    BITUACH_LEUMI_RESERVE_USAGE,
    BituachLeumiReserveCommand,
    format_bituach_leumi_reserve,
    parse_bituach_leumi_reserve_command,
)
from app.schemas.bituach_leumi import BituachLeumiReserveSummary
from app.services.bituach_leumi_reserve_service import (
    BituachLeumiReserveFinancialProfileNotFoundError,
)


def make_summary(**overrides: object) -> BituachLeumiReserveSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "deductible_expense_total": Decimal("2000.00"),
        "estimated_profit": Decimal("8000.00"),
        "reserve_percent": Decimal("0.12"),
        "estimated_bituach_leumi_reserve": Decimal("960.00"),
        "transactions_count": 8,
        "included_income_count": 5,
        "included_expense_count": 3,
        "skipped_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return BituachLeumiReserveSummary(**data)


def test_parse_bituach_leumi_reserve_validates_format() -> None:
    assert parse_bituach_leumi_reserve_command("/bituach_leumi_reserve") == (
        BITUACH_LEUMI_RESERVE_USAGE
    )
    assert parse_bituach_leumi_reserve_command(
        "/bituach_leumi_reserve 2026-05-01 invalid"
    ) == BITUACH_LEUMI_RESERVE_USAGE
    assert parse_bituach_leumi_reserve_command(
        "/bituach_leumi_reserve 2026-05-01 2026-06-30 extra"
    ) == BITUACH_LEUMI_RESERVE_USAGE


def test_parse_bituach_leumi_reserve_validates_date_order() -> None:
    assert parse_bituach_leumi_reserve_command(
        "/bituach_leumi_reserve 2026-06-30 2026-05-01"
    ) == "Period end must be after period start."
    assert parse_bituach_leumi_reserve_command(
        "/bituach_leumi_reserve 2026-05-01 2026-06-30"
    ) == BituachLeumiReserveCommand(date(2026, 5, 1), date(2026, 6, 30))


def test_format_bituach_leumi_reserve_includes_disclaimer() -> None:
    text = format_bituach_leumi_reserve(make_summary())

    assert "Income total: 10,000.00 ILS" in text
    assert "Deductible expenses: 2,000.00 ILS" in text
    assert "Estimated profit: 8,000.00 ILS" in text
    assert "Reserve percent: 12.00%" in text
    assert "Estimated Bituach Leumi reserve: 960.00 ILS" in text
    assert "Transactions counted: 8" in text
    assert (
        "This is an estimate for planning only. It is not an official "
        "Bituach Leumi calculation or filing."
    ) in text


def test_format_bituach_leumi_reserve_when_percent_is_missing() -> None:
    assert format_bituach_leumi_reserve(
        make_summary(
            reserve_percent=None,
            estimated_bituach_leumi_reserve=Decimal("0.00"),
        )
    ) == (
        "Bituach Leumi reserve percent is not set in financial profile.\n\n"
        "Set bituach_leumi_reserve_percent in bootstrap/profile settings.\n\n"
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


def test_bituach_leumi_reserve_handler_returns_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/bituach_leumi_reserve 2026-05-01 2026-06-30")
    calls: list[tuple[object, int, date, date]] = []

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_reserve(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> BituachLeumiReserveSummary:
        calls.append((session, user_id, period_start, period_end))
        return make_summary()

    monkeypatch.setattr(
        bituach_leumi,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        bituach_leumi,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(
        bituach_leumi,
        "get_bituach_leumi_reserve",
        fake_get_reserve,
    )

    asyncio.run(
        bituach_leumi.handle_bituach_leumi_reserve(  # type: ignore[arg-type]
            message
        )
    )

    assert calls[0][1:] == (7, date(2026, 5, 1), date(2026, 6, 30))
    assert message.answers == [format_bituach_leumi_reserve(make_summary())]


def test_handler_returns_clear_missing_profile_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/bituach_leumi_reserve 2026-05-01 2026-06-30")

    async def fake_get_or_create_user(**kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_reserve(
        *args: object,
        **kwargs: object,
    ) -> BituachLeumiReserveSummary:
        raise BituachLeumiReserveFinancialProfileNotFoundError("missing")

    monkeypatch.setattr(
        bituach_leumi,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        bituach_leumi,
        "get_or_create_user",
        fake_get_or_create_user,
    )
    monkeypatch.setattr(
        bituach_leumi,
        "get_bituach_leumi_reserve",
        fake_get_reserve,
    )

    asyncio.run(
        bituach_leumi.handle_bituach_leumi_reserve(  # type: ignore[arg-type]
            message
        )
    )

    assert message.answers == [
        "Financial profile is not set. Use bootstrap.yaml to load initial data."
    ]
