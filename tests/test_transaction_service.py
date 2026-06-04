import asyncio
from datetime import date
from decimal import Decimal

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import (
    create_transaction,
    get_last_transactions,
)


class FakeScalarResult:
    def __init__(self, transactions: list[Transaction]) -> None:
        self.transactions = transactions

    def all(self) -> list[Transaction]:
        return self.transactions


class FakeResult:
    def __init__(self, transactions: list[Transaction]) -> None:
        self.transactions = transactions

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.transactions)


class FakeSession:
    def __init__(self, transactions: list[Transaction] | None = None) -> None:
        self.added: Transaction | None = None
        self.committed = False
        self.refreshed: Transaction | None = None
        self.statement = None
        self.transactions = transactions or []

    def add(self, transaction: Transaction) -> None:
        self.added = transaction

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, transaction: Transaction) -> None:
        self.refreshed = transaction

    async def execute(self, statement: object) -> FakeResult:
        self.statement = statement
        return FakeResult(self.transactions)


def test_create_transaction_sets_manual_defaults() -> None:
    session = FakeSession()
    data = TransactionCreate(
        type="expense",
        amount=Decimal("42.50"),
        date=date(2026, 5, 27),
        category="transport",
    )

    transaction = asyncio.run(create_transaction(session, 7, data))  # type: ignore[arg-type]

    assert session.added is transaction
    assert session.committed is True
    assert session.refreshed is transaction
    assert transaction.user_id == 7
    assert transaction.amount_total == Decimal("42.50")
    assert transaction.vat_relevant is False
    assert transaction.business_use_percent == Decimal("100.00")
    assert transaction.balance_impact_type == "business"
    assert transaction.currency == "ILS"
    assert transaction.source == "manual"
    assert transaction.status == "confirmed"


def test_create_transaction_accepts_custom_source() -> None:
    session = FakeSession()
    data = TransactionCreate(
        type="income",
        amount=Decimal("1500"),
        date=date(2026, 5, 28),
        description="consulting",
    )

    transaction = asyncio.run(
        create_transaction(
            session, 7, data, source="ai_text", status="confirmed"  # type: ignore[arg-type]
        )
    )

    assert transaction.source == "ai_text"
    assert transaction.status == "confirmed"


def test_get_last_transactions_caps_limit_and_orders_results() -> None:
    transactions = [Transaction(user_id=3, type="income", amount=Decimal("1"), date=date(2026, 5, 27))]
    session = FakeSession(transactions)

    result = asyncio.run(get_last_transactions(session, 3, limit=100))  # type: ignore[arg-type]
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))

    assert result == transactions
    assert "WHERE transactions.user_id = 3" in sql
    assert "ORDER BY transactions.date DESC, transactions.created_at DESC" in sql
    assert "LIMIT 20" in sql
