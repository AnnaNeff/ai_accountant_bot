import asyncio
from datetime import date
from decimal import Decimal

from app.models.recurring_rule import RecurringRule
from app.services.recurring_service import (
    calculate_monthly_due_date,
    generate_recurring_transactions,
    should_generate_recurring_transaction,
)


def make_rule(**overrides: object) -> RecurringRule:
    data = {
        "user_id": 1,
        "type": "expense",
        "amount": Decimal("100.00"),
        "currency": "ILS",
        "description": "Rent",
        "frequency": "monthly",
        "day_of_month": 10,
        "start_date": date(2026, 1, 1),
        "active": True,
    }
    data.update(overrides)
    return RecurringRule(**data)


def test_calculate_monthly_due_date_for_regular_month() -> None:
    rule = make_rule(day_of_month=10)

    assert calculate_monthly_due_date(rule, date(2026, 5, 9)) is None
    assert calculate_monthly_due_date(rule, date(2026, 5, 10)) == date(2026, 5, 10)
    assert calculate_monthly_due_date(rule, date(2026, 5, 28)) == date(2026, 5, 10)


def test_calculate_monthly_due_date_caps_day_31_in_30_day_month() -> None:
    rule = make_rule(day_of_month=31)

    assert calculate_monthly_due_date(rule, date(2026, 4, 29)) is None
    assert calculate_monthly_due_date(rule, date(2026, 4, 30)) == date(2026, 4, 30)


def test_calculate_monthly_due_date_caps_february() -> None:
    rule = make_rule(day_of_month=31)

    assert calculate_monthly_due_date(rule, date(2026, 2, 27)) is None
    assert calculate_monthly_due_date(rule, date(2026, 2, 28)) == date(2026, 2, 28)


def test_should_generate_recurring_transaction_skips_duplicate_due_date() -> None:
    rule = make_rule(
        day_of_month=10,
        last_generated_for_date=date(2026, 5, 10),
    )

    assert should_generate_recurring_transaction(rule, date(2026, 5, 28)) is None


def test_should_generate_recurring_transaction_skips_later_generated_date() -> None:
    rule = make_rule(
        day_of_month=10,
        last_generated_for_date=date(2026, 5, 31),
    )

    assert should_generate_recurring_transaction(rule, date(2026, 5, 28)) is None


class FakeScalarResult:
    def __init__(self, rules: list[RecurringRule]) -> None:
        self.rules = rules

    def all(self) -> list[RecurringRule]:
        return self.rules


class FakeResult:
    def __init__(self, rules: list[RecurringRule]) -> None:
        self.rules = rules

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.rules)


class FakeSession:
    def __init__(self, rules: list[RecurringRule]) -> None:
        self.rules = rules
        self.added = []
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        return FakeResult(self.rules)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.committed = True


def test_generate_recurring_transactions_sets_transaction_defaults() -> None:
    rule = make_rule(
        user_id=7,
        type="income",
        amount=Decimal("3000.00"),
        category="services",
        description="Client payment",
        day_of_month=10,
    )
    session = FakeSession([rule])

    created_count = asyncio.run(
        generate_recurring_transactions(session, 7, today=date(2026, 5, 28))  # type: ignore[arg-type]
    )

    assert created_count == 1
    assert session.committed is True
    assert rule.last_generated_for_date == date(2026, 5, 10)
    assert len(session.added) == 1
    transaction = session.added[0]
    assert transaction.user_id == 7
    assert transaction.type == "income"
    assert transaction.amount == Decimal("3000.00")
    assert transaction.amount_total == Decimal("3000.00")
    assert transaction.vat_relevant is False
    assert transaction.business_use_percent == Decimal("100.00")
    assert transaction.balance_impact_type == "business"
    assert transaction.currency == "ILS"
    assert transaction.category == "services"
    assert transaction.description == "Client payment"
    assert transaction.source == "recurring"
    assert transaction.status == "confirmed"
    assert transaction.date == date(2026, 5, 10)
