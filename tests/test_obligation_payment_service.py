import asyncio
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.models.obligation_payment import ObligationPayment
from app.schemas.obligation_payment import ObligationPaymentCreate
from app.services.obligation_payment_service import (
    create_obligation_payment,
    find_existing_paid_obligation_payment,
    get_obligation_payments_for_rule,
    get_recent_obligation_payments,
)


class FakeScalarResult:
    def __init__(self, items: list[ObligationPayment]) -> None:
        self.items = items

    def all(self) -> list[ObligationPayment]:
        return self.items


class FakeResult:
    def __init__(self, items: list[ObligationPayment]) -> None:
        self.items = items

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.items)

    def scalar_one_or_none(self) -> ObligationPayment | None:
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, payments: list[ObligationPayment] | None = None) -> None:
        self.payments = payments or []
        self.added: ObligationPayment | None = None
        self.committed = False
        self.refreshed: ObligationPayment | None = None
        self.statement: Any | None = None

    def add(self, payment: ObligationPayment) -> None:
        self.added = payment

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, payment: ObligationPayment) -> None:
        self.refreshed = payment

    async def execute(self, statement: Any) -> FakeResult:
        self.statement = statement
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        matches = self.payments

        if "obligation_payments.user_id = 7" in sql:
            matches = [payment for payment in matches if payment.user_id == 7]
        if "obligation_payments.recurring_rule_id = 5" in sql:
            matches = [
                payment for payment in matches if payment.recurring_rule_id == 5
            ]
        period_start_match = re.search(
            r"obligation_payments\.period_start = '(\d{4}-\d{2}-\d{2})'",
            sql,
        )
        if period_start_match is not None:
            expected_period_start = date.fromisoformat(period_start_match.group(1))
            matches = [
                payment
                for payment in matches
                if payment.period_start == expected_period_start
            ]
        period_end_match = re.search(
            r"obligation_payments\.period_end = '(\d{4}-\d{2}-\d{2})'",
            sql,
        )
        if period_end_match is not None:
            expected_period_end = date.fromisoformat(period_end_match.group(1))
            matches = [
                payment
                for payment in matches
                if payment.period_end == expected_period_end
            ]
        if "obligation_payments.status = 'paid'" in sql:
            matches = [payment for payment in matches if payment.status == "paid"]

        return FakeResult(matches)


def make_payment(**overrides: object) -> ObligationPayment:
    data = {
        "id": 1,
        "user_id": 7,
        "recurring_rule_id": 5,
        "transaction_id": 123,
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "amount": Decimal("1200.00"),
        "currency": "ILS",
        "status": "paid",
        "created_at": datetime(2026, 6, 6),
    }
    data.update(overrides)
    return ObligationPayment(**data)


def test_create_obligation_payment_links_transaction() -> None:
    session = FakeSession()
    data = ObligationPaymentCreate(
        recurring_rule_id=5,
        transaction_id=123,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 6, 30),
        amount=Decimal("1200.00"),
        notes="VAT payment May-June",
    )

    payment = asyncio.run(
        create_obligation_payment(session, user_id=7, data=data)  # type: ignore[arg-type]
    )

    assert session.added is payment
    assert session.committed is True
    assert session.refreshed is payment
    assert payment.user_id == 7
    assert payment.transaction_id == 123
    assert payment.status == "paid"


def test_find_existing_paid_payment_matches_same_period() -> None:
    existing = make_payment()
    session = FakeSession([existing])

    result = asyncio.run(
        find_existing_paid_obligation_payment(
            session,  # type: ignore[arg-type]
            user_id=7,
            recurring_rule_id=5,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 6, 30),
        )
    )

    assert result is existing


def test_same_rule_different_period_is_allowed() -> None:
    existing = make_payment()
    session = FakeSession([existing])

    result = asyncio.run(
        find_existing_paid_obligation_payment(
            session,  # type: ignore[arg-type]
            user_id=7,
            recurring_rule_id=5,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 8, 31),
        )
    )

    assert result is None


def test_get_obligation_payments_for_rule_filters_user_and_rule() -> None:
    own = make_payment()
    other_rule = make_payment(id=2, recurring_rule_id=6)
    other_user = make_payment(id=3, user_id=8)
    session = FakeSession([own, other_rule, other_user])

    result = asyncio.run(
        get_obligation_payments_for_rule(
            session,  # type: ignore[arg-type]
            user_id=7,
            recurring_rule_id=5,
        )
    )

    assert result == [own]


def test_get_recent_obligation_payments_caps_limit() -> None:
    payment = make_payment()
    session = FakeSession([payment])

    result = asyncio.run(
        get_recent_obligation_payments(
            session,  # type: ignore[arg-type]
            user_id=7,
            limit=100,
        )
    )
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))

    assert result == [payment]
    assert "ORDER BY obligation_payments.created_at DESC" in sql
    assert "LIMIT 20" in sql
