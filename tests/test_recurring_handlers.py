import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.bot.handlers import recurring
from app.bot.handlers.recurring import (
    PAY_OBLIGATION_USAGE,
    format_generation_result,
    format_obligation_payments,
    format_obligation_statuses,
    format_obligations,
    format_recurring_rules,
    parse_pay_obligation_command,
)
from app.models.obligation_payment import ObligationPayment
from app.models.recurring_rule import RecurringRule
from app.services.obligation_status_service import ExpectedObligationPeriod


def make_rule(**overrides: object) -> RecurringRule:
    data = {
        "user_id": 1,
        "type": "expense",
        "amount": Decimal("1200.00"),
        "currency": "ILS",
        "description": "Loan payment",
        "frequency": "monthly",
        "day_of_month": 10,
        "payment_behavior": "auto_pay",
        "obligation_type": "loan",
        "affects_balance_when_generated": True,
        "start_date": date(2026, 1, 1),
        "active": True,
    }
    data.update(overrides)
    return RecurringRule(**data)


def test_format_recurring_rules_shows_payment_behavior_and_obligation_type() -> None:
    assert format_recurring_rules([make_rule()]) == (
        "Recurring rules:\n\n"
        "1. expense | 1,200.00 ILS | day 10 | auto_pay | loan | Loan payment"
    )


def test_format_obligations_shows_only_given_non_auto_pay_rules() -> None:
    rules = [
        make_rule(
            amount=Decimal("1.00"),
            description="VAT reserve",
            day_of_month=15,
            payment_behavior="reserve_only",
            obligation_type="vat",
        ),
        make_rule(
            amount=Decimal("500.00"),
            description="Bituach Leumi",
            day_of_month=15,
            payment_behavior="manual_pay",
            obligation_type="bituach_leumi",
        ),
    ]

    assert format_obligations(rules) == (
        "Obligations:\n\n"
        "1. reserve_only | vat | 1.00 ILS | day 15 | VAT reserve\n"
        "2. manual_pay | bituach_leumi | 500.00 ILS | day 15 | Bituach Leumi"
    )


def test_format_obligations_empty_message() -> None:
    assert format_obligations([]) == "No manual or reserve obligations yet."


def test_format_generation_result_mentions_skipped_obligations() -> None:
    assert format_generation_result(1, 2) == (
        "Generated recurring transactions: 1\n"
        "Skipped non-auto-pay obligations: 2"
    )
    assert format_generation_result(0, 2) == (
        "No recurring transactions to generate.\n"
        "Skipped non-auto-pay obligations: 2"
    )
    assert format_generation_result(0, 0) == "No recurring transactions to generate."


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=12345, full_name="Test User")
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


class FakeSessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def test_parse_pay_obligation_command_validates_format() -> None:
    assert parse_pay_obligation_command("/pay_obligation") == PAY_OBLIGATION_USAGE
    assert (
        parse_pay_obligation_command("/pay_obligation 5 1200 VAT payment")
        == PAY_OBLIGATION_USAGE
    )
    assert (
        parse_pay_obligation_command(
            "/pay_obligation five 1200 2026-05-01 2026-06-30"
        )
        == PAY_OBLIGATION_USAGE
    )
    assert (
        parse_pay_obligation_command(
            "/pay_obligation 5 0 2026-05-01 2026-06-30"
        )
        == PAY_OBLIGATION_USAGE
    )
    assert (
        parse_pay_obligation_command(
            "/pay_obligation 5 1200 2026-06-30 2026-05-01"
        )
        == PAY_OBLIGATION_USAGE
    )

    command = parse_pay_obligation_command(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 VAT payment May-June"
    )
    assert not isinstance(command, str)
    assert command.rule_id == 5
    assert command.amount == Decimal("1200")
    assert command.period_start == date(2026, 5, 1)
    assert command.period_end == date(2026, 6, 30)
    assert command.description == "VAT payment May-June"


def setup_payment_handler(
    monkeypatch: pytest.MonkeyPatch,
    rule: RecurringRule | None,
    *,
    duplicate: bool = False,
) -> dict[str, Any]:
    created: dict[str, Any] = {}

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_recurring_rule_by_id(
        session: object,
        **kwargs: Any,
    ) -> RecurringRule | None:
        assert kwargs["user_id"] == 7
        assert kwargs["rule_id"] == 5
        return rule

    async def fake_find_existing_paid_obligation_payment(
        session: object,
        **kwargs: Any,
    ) -> object | None:
        created["duplicate_check"] = kwargs
        return SimpleNamespace(id=99) if duplicate else None

    async def fake_create_transaction(
        session: object,
        **kwargs: Any,
    ) -> Any:
        created.update(kwargs)
        return SimpleNamespace(
            id=123,
            amount=kwargs["data"].amount,
            currency=kwargs["data"].currency,
        )

    async def fake_create_obligation_payment(
        session: object,
        **kwargs: Any,
    ) -> Any:
        created["payment"] = kwargs
        return SimpleNamespace(id=77)

    monkeypatch.setattr(recurring, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(recurring, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(
        recurring,
        "get_recurring_rule_by_id",
        fake_get_recurring_rule_by_id,
    )
    monkeypatch.setattr(
        recurring,
        "find_existing_paid_obligation_payment",
        fake_find_existing_paid_obligation_payment,
    )
    monkeypatch.setattr(recurring, "create_transaction", fake_create_transaction)
    monkeypatch.setattr(
        recurring,
        "create_obligation_payment",
        fake_create_obligation_payment,
    )
    return created


def test_pay_obligation_unknown_rule_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 VAT payment"
    )
    setup_payment_handler(monkeypatch, None)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    assert message.answers == ["Obligation not found."]


@pytest.mark.parametrize(
    ("behavior", "expected"),
    [
        (
            "auto_pay",
            "This obligation is auto-pay. It is handled by /generate_recurring.",
        ),
        (
            "reserve_only",
            "This obligation is reserve-only and cannot be paid directly. "
            "Create a manual expense if needed.",
        ),
    ],
)
def test_pay_obligation_rejects_non_manual_rules(
    monkeypatch: pytest.MonkeyPatch,
    behavior: str,
    expected: str,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 payment"
    )
    rule = make_rule(id=5, payment_behavior=behavior)
    created = setup_payment_handler(monkeypatch, rule)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    assert message.answers == [expected]
    assert "data" not in created


@pytest.mark.parametrize(
    ("obligation_type", "expected_impact"),
    [
        ("vat", "tax_payment"),
        ("income_tax", "tax_payment"),
        ("bituach_leumi", "tax_payment"),
        ("other_tax", "tax_payment"),
        ("loan", "business"),
    ],
)
def test_pay_obligation_manual_rule_creates_confirmed_transaction(
    monkeypatch: pytest.MonkeyPatch,
    obligation_type: str,
    expected_impact: str,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 Paid obligation"
    )
    rule = make_rule(
        id=5,
        payment_behavior="manual_pay",
        obligation_type=obligation_type,
        category="tax" if obligation_type == "vat" else "loan",
    )
    created = setup_payment_handler(monkeypatch, rule)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    data = created["data"]
    assert created["user_id"] == 7
    assert created["source"] == "obligation_manual_payment"
    assert created["status"] == "confirmed"
    assert created["commit"] is False
    assert data.type == "expense"
    assert data.amount == Decimal("1200")
    assert data.amount_total == Decimal("1200")
    assert data.currency == "ILS"
    assert data.date == date.today()
    assert data.category == rule.category
    assert data.description == "Paid obligation"
    assert data.balance_impact_type == expected_impact
    payment_data = created["payment"]["data"]
    assert created["payment"]["user_id"] == 7
    assert payment_data.recurring_rule_id == 5
    assert payment_data.transaction_id == 123
    assert payment_data.period_start == date(2026, 5, 1)
    assert payment_data.period_end == date(2026, 6, 30)
    assert payment_data.amount == Decimal("1200")
    assert payment_data.currency == "ILS"
    assert payment_data.status == "paid"
    assert payment_data.notes == "Paid obligation"
    assert message.answers == [
        "Obligation payment saved.\n\n"
        "Rule ID: 5\n"
        f"Type: {obligation_type}\n"
        "Amount: 1200.00 ILS\n"
        "Transaction ID: 123"
    ]


def test_pay_obligation_uses_rule_description_when_description_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 650 2026-06-01 2026-06-30"
    )
    rule = make_rule(
        id=5,
        description="Bituach Leumi",
        payment_behavior="manual_pay",
        obligation_type="bituach_leumi",
    )
    created = setup_payment_handler(monkeypatch, rule)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    assert created["data"].description == "Bituach Leumi"


def test_pay_obligation_rejects_unexpected_payment_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 payment"
    )
    rule = make_rule(id=5, payment_behavior="unexpected")
    created = setup_payment_handler(monkeypatch, rule)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    assert message.answers == ["Obligation not found."]
    assert "data" not in created


def test_pay_obligation_duplicate_is_not_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(
        "/pay_obligation 5 1200 2026-05-01 2026-06-30 VAT payment"
    )
    rule = make_rule(
        id=5,
        payment_behavior="manual_pay",
        obligation_type="vat",
        category="tax",
    )
    created = setup_payment_handler(monkeypatch, rule, duplicate=True)

    asyncio.run(recurring.handle_pay_obligation(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Obligation payment for this period already exists. Not created."
    ]
    assert "data" not in created
    assert "payment" not in created


def test_format_obligation_payments_shows_recent_payments() -> None:
    payments = [
        ObligationPayment(
            user_id=7,
            recurring_rule_id=5,
            transaction_id=123,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 6, 30),
            amount=Decimal("1200.00"),
            currency="ILS",
            status="paid",
        ),
        ObligationPayment(
            user_id=7,
            recurring_rule_id=7,
            transaction_id=124,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            amount=Decimal("650.00"),
            currency="ILS",
            status="paid",
        ),
    ]

    assert format_obligation_payments(payments) == (
        "Obligation payments:\n\n"
        "1. paid | rule 5 | 2026-05-01..2026-06-30 | "
        "1,200.00 ILS | transaction 123\n"
        "2. paid | rule 7 | 2026-06-01..2026-06-30 | "
        "650.00 ILS | transaction 124"
    )


def test_format_obligation_payments_empty_message() -> None:
    assert format_obligation_payments([]) == "No obligation payments yet."


def test_handle_obligation_payments_shows_recent_user_payments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/obligation_payments")
    payment = ObligationPayment(
        user_id=7,
        recurring_rule_id=5,
        transaction_id=123,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 6, 30),
        amount=Decimal("1200.00"),
        currency="ILS",
        status="paid",
    )

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_recent_obligation_payments(
        session: object,
        **kwargs: Any,
    ) -> list[ObligationPayment]:
        assert kwargs == {"user_id": 7, "limit": 10}
        return [payment]

    monkeypatch.setattr(recurring, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(recurring, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(
        recurring,
        "get_recent_obligation_payments",
        fake_get_recent_obligation_payments,
    )

    asyncio.run(recurring.handle_obligation_payments(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Obligation payments:\n\n"
        "1. paid | rule 5 | 2026-05-01..2026-06-30 | "
        "1,200.00 ILS | transaction 123"
    ]


def make_status(**overrides: object) -> ExpectedObligationPeriod:
    data = {
        "rule_id": 5,
        "description": "VAT payment",
        "obligation_type": "vat",
        "payment_behavior": "manual_pay",
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "due_date": date(2026, 7, 15),
        "status": "unpaid",
        "amount": Decimal("1.00"),
        "currency": "ILS",
        "transaction_id": None,
    }
    data.update(overrides)
    return ExpectedObligationPeriod(**data)  # type: ignore[arg-type]


def test_format_obligation_statuses_shows_all_statuses() -> None:
    statuses = [
        make_status(),
        make_status(
            rule_id=6,
            description="Bituach Leumi",
            obligation_type="bituach_leumi",
            period_start=date(2026, 6, 1),
            due_date=date(2026, 6, 15),
            status="paid",
            transaction_id=123,
        ),
        make_status(
            rule_id=7,
            description="Income tax",
            obligation_type="income_tax",
            period_start=date(2026, 4, 1),
            due_date=date(2026, 7, 15),
            status="overdue",
        ),
    ]

    assert format_obligation_statuses(statuses) == (
        "Obligation status:\n\n"
        "1. VAT payment | vat | 2026-05-01..2026-06-30 | "
        "due 2026-07-15 | unpaid | 1.00 ILS\n"
        "2. Bituach Leumi | bituach_leumi | 2026-06-01..2026-06-30 | "
        "due 2026-06-15 | paid | 1.00 ILS | transaction 123\n"
        "3. Income tax | income_tax | 2026-04-01..2026-06-30 | "
        "due 2026-07-15 | overdue | 1.00 ILS"
    )


def test_format_obligation_statuses_empty_message() -> None:
    assert format_obligation_statuses([]) == "No obligation periods found."


def test_handle_obligation_status_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/obligation_status")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_obligation_statuses(
        session: object,
        **kwargs: Any,
    ) -> list[ExpectedObligationPeriod]:
        assert kwargs["user_id"] == 7
        assert kwargs["today"] == date.today()
        return [make_status(status="overdue")]

    async def fail_create(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Status command must not create records.")

    monkeypatch.setattr(recurring, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(recurring, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(
        recurring,
        "get_obligation_statuses",
        fake_get_obligation_statuses,
    )
    monkeypatch.setattr(recurring, "create_transaction", fail_create)
    monkeypatch.setattr(recurring, "create_obligation_payment", fail_create)

    asyncio.run(recurring.handle_obligation_status(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Obligation status:\n\n"
        "1. VAT payment | vat | 2026-05-01..2026-06-30 | "
        "due 2026-07-15 | overdue | 1.00 ILS"
    ]


def test_handle_obligation_status_empty_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/obligation_status")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_obligation_statuses(
        session: object,
        **kwargs: Any,
    ) -> list[ExpectedObligationPeriod]:
        return []

    monkeypatch.setattr(recurring, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(recurring, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(
        recurring,
        "get_obligation_statuses",
        fake_get_obligation_statuses,
    )

    asyncio.run(recurring.handle_obligation_status(message))  # type: ignore[arg-type]

    assert message.answers == ["No obligation periods found."]
