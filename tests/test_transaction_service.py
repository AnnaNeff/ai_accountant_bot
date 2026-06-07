import asyncio
from datetime import date
from decimal import Decimal

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import (
    create_transaction,
    get_last_transactions,
    has_similar_obligation_payment_today,
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
        self.flushed = False
        self.statement = None
        self.transactions = transactions or []

    def add(self, transaction: Transaction) -> None:
        self.added = transaction

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, transaction: Transaction) -> None:
        self.refreshed = transaction

    async def flush(self) -> None:
        self.flushed = True
        if self.added is not None and self.added.id is None:
            self.added.id = 123

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


def test_create_transaction_can_defer_commit_for_atomic_linked_record() -> None:
    session = FakeSession()
    data = TransactionCreate(
        type="expense",
        amount=Decimal("1200.00"),
        date=date(2026, 6, 6),
        description="VAT payment",
    )

    transaction = asyncio.run(
        create_transaction(
            session,  # type: ignore[arg-type]
            user_id=7,
            data=data,
            source="obligation_manual_payment",
            status="confirmed",
            commit=False,
        )
    )

    assert transaction.id == 123
    assert session.flushed is True
    assert session.committed is False
    assert session.refreshed is None


def test_get_last_transactions_caps_limit_and_orders_results() -> None:
    transactions = [Transaction(user_id=3, type="income", amount=Decimal("1"), date=date(2026, 5, 27))]
    session = FakeSession(transactions)

    result = asyncio.run(get_last_transactions(session, 3, limit=100))  # type: ignore[arg-type]
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))

    assert result == transactions
    assert "WHERE transactions.user_id = 3" in sql
    assert "ORDER BY transactions.date DESC, transactions.created_at DESC" in sql
    assert "LIMIT 20" in sql


def test_similar_obligation_payment_matches_description_containment() -> None:
    session = FakeSession(
        [
            Transaction(
                user_id=7,
                type="expense",
                amount=Decimal("1200.00"),
                currency="ILS",
                date=date(2026, 6, 6),
                category="tax",
                description="VAT payment May-June",
                source="obligation_manual_payment",
                status="confirmed",
            )
        ]
    )

    exists = asyncio.run(
        has_similar_obligation_payment_today(
            session,  # type: ignore[arg-type]
            user_id=7,
            amount=Decimal("1200.00"),
            category="tax",
            descriptions=("VAT payment", "VAT reserve"),
            payment_date=date(2026, 6, 6),
        )
    )

    assert exists is True
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.source = 'obligation_manual_payment'" in sql
    assert "transactions.date = '2026-06-06'" in sql
