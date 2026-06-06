import asyncio
from datetime import date
from decimal import Decimal

from app.models.recurring_rule import RecurringRule
from app.services.recurring_service import (
    calculate_monthly_due_date,
    generate_recurring_transactions,
    get_active_non_auto_pay_obligations,
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
        "payment_behavior": "auto_pay",
        "obligation_type": "regular",
        "affects_balance_when_generated": True,
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
        self.statement = None

    async def execute(self, statement: object) -> FakeResult:
        self.statement = statement
        return FakeResult(self.rules)

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.committed = True


def test_get_active_non_auto_pay_obligations_filters_supported_behaviors() -> None:
    session = FakeSession([])

    result = asyncio.run(
        get_active_non_auto_pay_obligations(session, 7)  # type: ignore[arg-type]
    )
    sql = str(
        session.statement.compile(
            compile_kwargs={"literal_binds": True},
        )
    )

    assert result == []
    assert "recurring_rules.user_id = 7" in sql
    assert "recurring_rules.active IS true" in sql
    assert "recurring_rules.payment_behavior IN ('manual_pay', 'reserve_only')" in sql


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

    result = asyncio.run(
        generate_recurring_transactions(session, 7, today=date(2026, 5, 28))  # type: ignore[arg-type]
    )

    assert result.generated_count == 1
    assert result.skipped_non_auto_pay_count == 0
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


def test_generate_recurring_transactions_skips_manual_pay() -> None:
    rule = make_rule(user_id=7, payment_behavior="manual_pay")
    session = FakeSession([rule])

    result = asyncio.run(
        generate_recurring_transactions(session, 7, today=date(2026, 5, 28))  # type: ignore[arg-type]
    )

    assert result.generated_count == 0
    assert result.skipped_non_auto_pay_count == 1
    assert session.added == []
    assert session.committed is False
    assert rule.last_generated_for_date is None


def test_generate_recurring_transactions_skips_reserve_only() -> None:
    rule = make_rule(user_id=7, payment_behavior="reserve_only", obligation_type="vat")
    session = FakeSession([rule])

    result = asyncio.run(
        generate_recurring_transactions(session, 7, today=date(2026, 5, 28))  # type: ignore[arg-type]
    )

    assert result.generated_count == 0
    assert result.skipped_non_auto_pay_count == 1
    assert session.added == []
    assert session.committed is False
    assert rule.last_generated_for_date is None


def test_generate_recurring_transactions_only_creates_auto_pay_transactions() -> None:
    auto_pay = make_rule(
        user_id=7,
        amount=Decimal("1200.00"),
        payment_behavior="auto_pay",
        obligation_type="loan",
    )
    manual_pay = make_rule(
        user_id=7,
        amount=Decimal("500.00"),
        payment_behavior="manual_pay",
        obligation_type="bituach_leumi",
    )
    reserve_only = make_rule(
        user_id=7,
        amount=Decimal("1.00"),
        payment_behavior="reserve_only",
        obligation_type="vat",
    )
    session = FakeSession([auto_pay, manual_pay, reserve_only])

    result = asyncio.run(
        generate_recurring_transactions(session, 7, today=date(2026, 5, 28))  # type: ignore[arg-type]
    )

    assert result.generated_count == 1
    assert result.skipped_non_auto_pay_count == 2
    assert len(session.added) == 1
    assert session.added[0].amount == Decimal("1200.00")
    assert auto_pay.last_generated_for_date == date(2026, 5, 10)
    assert manual_pay.last_generated_for_date is None
    assert reserve_only.last_generated_for_date is None
