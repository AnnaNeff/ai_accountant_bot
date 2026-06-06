from datetime import date
from decimal import Decimal

import pytest

from app.schemas.recurring_rule import RecurringRuleCreate


def make_rule(**overrides: object) -> RecurringRuleCreate:
    data = {
        "type": "expense",
        "amount": Decimal("100.00"),
        "description": "rent",
        "frequency": "monthly",
        "day_of_month": 1,
        "start_date": date(2026, 5, 28),
    }
    data.update(overrides)
    return RecurringRuleCreate(**data)


def test_recurring_rule_create_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError, match="Amount must be a positive number"):
        make_rule(amount=Decimal("0"))

    with pytest.raises(ValueError, match="Amount must be a positive number"):
        make_rule(amount=Decimal("-1"))


def test_recurring_rule_create_rejects_non_finite_amount() -> None:
    with pytest.raises(ValueError):
        make_rule(amount=Decimal("NaN"))


def test_recurring_rule_create_rejects_day_outside_month_range() -> None:
    with pytest.raises(ValueError):
        make_rule(day_of_month=0)

    with pytest.raises(ValueError):
        make_rule(day_of_month=32)


def test_recurring_rule_create_accepts_only_monthly_frequency() -> None:
    assert make_rule(frequency="monthly").frequency == "monthly"

    with pytest.raises(ValueError):
        make_rule(frequency="weekly")


def test_recurring_rule_create_accepts_only_income_or_expense_type() -> None:
    assert make_rule(type="income").type == "income"
    assert make_rule(type="expense").type == "expense"

    with pytest.raises(ValueError):
        make_rule(type="transfer")


def test_recurring_rule_create_validates_payment_behavior() -> None:
    assert make_rule(payment_behavior="auto_pay").payment_behavior == "auto_pay"
    assert make_rule(payment_behavior="manual_pay").payment_behavior == "manual_pay"
    assert make_rule(payment_behavior="reserve_only").payment_behavior == "reserve_only"

    with pytest.raises(ValueError):
        make_rule(payment_behavior="automatic")


def test_recurring_rule_create_validates_obligation_type() -> None:
    assert make_rule(obligation_type="regular").obligation_type == "regular"
    assert make_rule(obligation_type="vat").obligation_type == "vat"
    assert make_rule(obligation_type="bituach_leumi").obligation_type == "bituach_leumi"

    with pytest.raises(ValueError):
        make_rule(obligation_type="unsupported_tax")
