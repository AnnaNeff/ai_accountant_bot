import asyncio
import re
from datetime import date
from decimal import Decimal

import pytest

from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.services.balance_service import (
    FinancialProfileNotFoundError,
    get_balance_summary,
)


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class FakeProfileResult:
    def __init__(self, profile: FinancialProfile | None) -> None:
        self.profile = profile

    def scalar_one_or_none(self) -> FinancialProfile | None:
        return self.profile


class FakeTransactionsResult:
    def __init__(self, transactions: list[Transaction]) -> None:
        self.transactions = transactions

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.transactions)


class FakeSession:
    def __init__(
        self,
        profile: FinancialProfile | None,
        transactions: list[Transaction] | None = None,
    ) -> None:
        self.profile = profile
        self.transactions = transactions or []
        self.statements: list[object] = []

    async def execute(self, statement: object) -> object:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return FakeProfileResult(self.profile)

        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        user_id_match = re.search(r"transactions\.user_id = (\d+)", sql)
        has_confirmed_filter = "transactions.status = 'confirmed'" in sql
        if user_id_match is None or not has_confirmed_filter:
            return FakeTransactionsResult(self.transactions)

        user_id = int(user_id_match.group(1))
        return FakeTransactionsResult(
            [
                transaction
                for transaction in self.transactions
                if transaction.user_id == user_id and transaction.status == "confirmed"
            ]
        )


def make_profile(**overrides: object) -> FinancialProfile:
    data = {
        "user_id": 1,
        "opening_balance": Decimal("1000.00"),
        "currency": "ILS",
        "opening_balance_date": date(2026, 5, 1),
    }
    data.update(overrides)
    return FinancialProfile(**data)


def make_transaction(**overrides: object) -> Transaction:
    data = {
        "user_id": 1,
        "type": "income",
        "amount": Decimal("100.00"),
        "currency": "ILS",
        "date": date(2026, 5, 28),
        "source": "manual",
        "status": "confirmed",
    }
    data.update(overrides)
    return Transaction(**data)


def test_balance_without_transactions_uses_opening_balance() -> None:
    session = FakeSession(profile=make_profile())

    summary = asyncio.run(get_balance_summary(session, 1))  # type: ignore[arg-type]

    assert summary.opening_balance == Decimal("1000.00")
    assert summary.currency == "ILS"
    assert summary.opening_balance_date == date(2026, 5, 1)
    assert summary.income_total == Decimal("0")
    assert summary.expense_total == Decimal("0")
    assert summary.current_balance == Decimal("1000.00")
    assert summary.transactions_count == 0


def test_balance_with_income_and_expense() -> None:
    session = FakeSession(
        profile=make_profile(opening_balance=Decimal("500.00")),
        transactions=[
            make_transaction(type="income", amount=Decimal("1200.00")),
            make_transaction(type="expense", amount=Decimal("350.25")),
        ],
    )

    summary = asyncio.run(get_balance_summary(session, 1))  # type: ignore[arg-type]

    assert summary.income_total == Decimal("1200.00")
    assert summary.expense_total == Decimal("350.25")
    assert summary.current_balance == Decimal("1349.75")
    assert summary.transactions_count == 2


def test_balance_ignores_transactions_from_other_users() -> None:
    session = FakeSession(
        profile=make_profile(opening_balance=Decimal("0.00")),
        transactions=[
            make_transaction(user_id=1, type="income", amount=Decimal("100.00")),
            make_transaction(user_id=2, type="income", amount=Decimal("900.00")),
            make_transaction(user_id=2, type="expense", amount=Decimal("50.00")),
        ],
    )

    summary = asyncio.run(get_balance_summary(session, 1))  # type: ignore[arg-type]

    assert summary.income_total == Decimal("100.00")
    assert summary.expense_total == Decimal("0")
    assert summary.current_balance == Decimal("100.00")
    assert summary.transactions_count == 1

    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.user_id = 1" in sql
    assert "transactions.status = 'confirmed'" in sql


def test_balance_ignores_non_confirmed_transactions() -> None:
    session = FakeSession(
        profile=make_profile(opening_balance=Decimal("0.00")),
        transactions=[
            make_transaction(type="income", amount=Decimal("200.00")),
            make_transaction(type="income", amount=Decimal("800.00"), status="pending"),
            make_transaction(type="expense", amount=Decimal("75.00"), status="draft"),
        ],
    )

    summary = asyncio.run(get_balance_summary(session, 1))  # type: ignore[arg-type]

    assert summary.income_total == Decimal("200.00")
    assert summary.expense_total == Decimal("0")
    assert summary.current_balance == Decimal("200.00")
    assert summary.transactions_count == 1

    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.user_id = 1" in sql
    assert "transactions.status = 'confirmed'" in sql


def test_balance_requires_financial_profile() -> None:
    session = FakeSession(profile=None)

    with pytest.raises(FinancialProfileNotFoundError) as error:
        asyncio.run(get_balance_summary(session, 1))  # type: ignore[arg-type]

    assert "user_id=1" in str(error.value)
    assert len(session.statements) == 1
