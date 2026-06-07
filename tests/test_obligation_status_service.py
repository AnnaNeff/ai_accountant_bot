import asyncio
from datetime import date
from decimal import Decimal

from app.models.obligation_payment import ObligationPayment
from app.models.recurring_rule import RecurringRule
from app.services.obligation_status_service import get_obligation_statuses


def make_rule(**overrides: object) -> RecurringRule:
    data = {
        "id": 5,
        "user_id": 7,
        "type": "expense",
        "amount": Decimal("1.00"),
        "currency": "ILS",
        "description": "Bituach Leumi",
        "frequency": "monthly",
        "day_of_month": 15,
        "period_months": 1,
        "due_day": 15,
        "due_month_offset": 0,
        "payment_behavior": "manual_pay",
        "obligation_type": "bituach_leumi",
        "affects_balance_when_generated": False,
        "start_date": date(2026, 1, 1),
        "active": True,
    }
    data.update(overrides)
    return RecurringRule(**data)


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class FakeResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.items)


class FakeSession:
    def __init__(
        self,
        rules: list[RecurringRule],
        payments: list[ObligationPayment] | None = None,
    ) -> None:
        self.results = [rules, payments or []]
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.results.pop(0))


def get_statuses(
    rules: list[RecurringRule],
    *,
    payments: list[ObligationPayment] | None = None,
    today: date = date(2026, 6, 15),
    months_back: int = 0,
    months_forward: int = 0,
) -> tuple[list[object], FakeSession]:
    session = FakeSession(rules, payments)
    statuses = asyncio.run(
        get_obligation_statuses(
            session,  # type: ignore[arg-type]
            user_id=7,
            today=today,
            months_back=months_back,
            months_forward=months_forward,
        )
    )
    return statuses, session


def test_expected_period_generation_for_monthly_rule() -> None:
    statuses, _ = get_statuses([make_rule()])

    assert len(statuses) == 1
    assert statuses[0].period_start == date(2026, 6, 1)
    assert statuses[0].period_end == date(2026, 6, 30)
    assert statuses[0].due_date == date(2026, 6, 15)


def test_due_date_with_zero_month_offset_stays_in_period_end_month() -> None:
    statuses, _ = get_statuses(
        [make_rule(due_day=20, due_month_offset=0)],
        today=date(2026, 6, 1),
    )

    assert statuses[0].due_date == date(2026, 6, 20)


def test_expected_period_generation_for_two_month_vat_rule() -> None:
    rule = make_rule(
        description="VAT payment",
        obligation_type="vat",
        period_months=2,
        due_month_offset=1,
        start_date=date(2026, 5, 1),
    )

    statuses, _ = get_statuses([rule])

    assert len(statuses) == 1
    assert statuses[0].period_start == date(2026, 5, 1)
    assert statuses[0].period_end == date(2026, 6, 30)
    assert statuses[0].due_date == date(2026, 7, 15)


def test_due_date_caps_day_to_end_of_month() -> None:
    statuses, _ = get_statuses(
        [make_rule(due_day=31, start_date=date(2026, 2, 1))],
        today=date(2026, 2, 1),
    )

    assert statuses[0].period_end == date(2026, 2, 28)
    assert statuses[0].due_date == date(2026, 2, 28)


def test_paid_status_requires_matching_paid_payment() -> None:
    payment = ObligationPayment(
        user_id=7,
        recurring_rule_id=5,
        transaction_id=123,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        amount=Decimal("1.00"),
        currency="ILS",
        status="paid",
    )

    statuses, _ = get_statuses([make_rule()], payments=[payment])

    assert statuses[0].status == "paid"
    assert statuses[0].transaction_id == 123


def test_unpaid_status_when_due_date_is_today_or_later() -> None:
    statuses, _ = get_statuses([make_rule()], today=date(2026, 6, 15))
    assert statuses[0].status == "unpaid"


def test_overdue_status_when_due_date_is_before_today() -> None:
    statuses, _ = get_statuses([make_rule()], today=date(2026, 6, 16))
    assert statuses[0].status == "overdue"


def test_auto_pay_rules_and_other_users_are_filtered_by_query() -> None:
    statuses, session = get_statuses([])

    assert statuses == []
    assert len(session.statements) == 1
    sql = str(
        session.statements[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "recurring_rules.user_id = 7" in sql
    assert "recurring_rules.payment_behavior IN ('manual_pay', 'reserve_only')" in sql


def test_only_current_user_paid_payments_are_queried() -> None:
    _, session = get_statuses([make_rule()])

    sql = str(
        session.statements[1].compile(compile_kwargs={"literal_binds": True})
    )
    assert "obligation_payments.user_id = 7" in sql
    assert "obligation_payments.recurring_rule_id IN (5)" in sql
    assert "obligation_payments.status = 'paid'" in sql
