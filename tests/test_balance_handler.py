import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.bot.handlers import balance as balance_handler
from app.schemas.balance import BalanceSummary
from app.services.balance_service import FinancialProfileNotFoundError


class FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=123, full_name="Test User")
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def make_summary(**overrides: object) -> BalanceSummary:
    data = {
        "opening_balance": Decimal("10000.00"),
        "currency": "ILS",
        "opening_balance_date": date(2026, 5, 1),
        "income_total": Decimal("4500.00"),
        "expense_total": Decimal("1300.00"),
        "current_balance": Decimal("13200.00"),
        "transactions_count": 5,
    }
    data.update(overrides)
    return BalanceSummary(**data)


def test_format_balance_summary() -> None:
    assert balance_handler.format_balance_summary(make_summary()) == (
        "Balance summary:\n\n"
        "Opening balance: 10,000.00 ILS\n"
        "Opening balance date: 2026-05-01\n\n"
        "Income total: 4,500.00 ILS\n"
        "Expense total: 1,300.00 ILS\n\n"
        "Current balance: 13,200.00 ILS\n"
        "Transactions counted: 5"
    )


def test_handle_balance_sends_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage()

    async def fake_get_or_create_user(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_balance_summary(*args: object, **kwargs: object) -> BalanceSummary:
        return make_summary()

    monkeypatch.setattr(
        balance_handler,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(balance_handler, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(balance_handler, "get_balance_summary", fake_get_balance_summary)

    asyncio.run(balance_handler.handle_balance(message))  # type: ignore[arg-type]

    assert message.answers == [balance_handler.format_balance_summary(make_summary())]


def test_handle_balance_when_profile_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage()

    async def fake_get_or_create_user(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(id=7)

    async def fake_get_balance_summary(*args: object, **kwargs: object) -> BalanceSummary:
        raise FinancialProfileNotFoundError("missing")

    monkeypatch.setattr(
        balance_handler,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(balance_handler, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(balance_handler, "get_balance_summary", fake_get_balance_summary)

    asyncio.run(balance_handler.handle_balance(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Financial profile is not set. Use bootstrap.yaml to load initial data."
    ]
