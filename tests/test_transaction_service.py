import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import (
    create_transaction,
    get_last_transactions,
    get_transaction_by_id,
    has_similar_obligation_payment_today,
    update_transaction_tax_field,
    validate_transaction_tax_field_value,
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

    def scalar_one_or_none(self) -> Transaction | None:
        return self.transactions[0] if self.transactions else None


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


def test_get_transaction_by_id_filters_transaction_and_user() -> None:
    transaction = Transaction(
        id=123,
        user_id=7,
        type="expense",
        amount=Decimal("10.00"),
        date=date(2026, 6, 7),
    )
    session = FakeSession([transaction])

    result = asyncio.run(
        get_transaction_by_id(
            session,  # type: ignore[arg-type]
            user_id=7,
            transaction_id=123,
        )
    )
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))

    assert result is transaction
    assert "transactions.id = 123" in sql
    assert "transactions.user_id = 7" in sql


def test_update_transaction_tax_field_commits_and_refreshes() -> None:
    transaction = Transaction(
        id=123,
        user_id=7,
        type="expense",
        amount=Decimal("10.00"),
        date=date(2026, 6, 7),
        vat_relevant=False,
    )
    session = FakeSession([transaction])

    result = asyncio.run(
        update_transaction_tax_field(
            session,  # type: ignore[arg-type]
            user_id=7,
            transaction_id=123,
            field="vat_relevant",
            value=True,
        )
    )

    assert result is transaction
    assert transaction.vat_relevant is True
    assert session.committed is True
    assert session.refreshed is transaction


def test_update_transaction_tax_field_rejects_forbidden_field() -> None:
    session = FakeSession([])

    try:
        asyncio.run(
            update_transaction_tax_field(
                session,  # type: ignore[arg-type]
                user_id=7,
                transaction_id=123,
                field="amount",
                value=Decimal("999"),
            )
        )
    except ValueError as error:
        assert str(error) == "Unsupported transaction tax field."
    else:
        raise AssertionError("Forbidden field update was accepted.")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount_total", Decimal("-0.01")),
        ("amount_net", Decimal("NaN")),
        ("vat_amount", "18"),
        ("vat_rate", Decimal("1.01")),
        ("business_use_percent", Decimal("100.01")),
        ("vat_included", 1),
        ("vat_relevant", "true"),
        ("tax_deductible", None),
        ("tax_category", ""),
        ("tax_category", "x" * 256),
        ("balance_impact_type", "unknown"),
    ],
)
def test_service_rejects_invalid_tax_field_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="Invalid transaction tax field value"):
        validate_transaction_tax_field_value(field, value)


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "user_id",
        "type",
        "amount",
        "currency",
        "date",
        "source",
        "status",
        "created_at",
        "updated_at",
    ],
)
def test_service_rejects_all_forbidden_transaction_fields(field: str) -> None:
    with pytest.raises(ValueError, match="Unsupported transaction tax field"):
        validate_transaction_tax_field_value(field, "value")


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
