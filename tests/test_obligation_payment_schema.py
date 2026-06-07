from datetime import date
from decimal import Decimal

import pytest

from app.schemas.obligation_payment import ObligationPaymentCreate


def make_payment(**overrides: object) -> ObligationPaymentCreate:
    data = {
        "recurring_rule_id": 5,
        "period_start": date(2026, 5, 1),
        "period_end": date(2026, 6, 30),
        "amount": Decimal("1200.00"),
    }
    data.update(overrides)
    return ObligationPaymentCreate(**data)


def test_obligation_payment_schema_validates_amount() -> None:
    with pytest.raises(ValueError, match="Amount must be a positive number"):
        make_payment(amount=Decimal("0"))

    with pytest.raises(ValueError, match="Amount must be a positive number"):
        make_payment(amount=Decimal("-1"))


def test_obligation_payment_schema_validates_period() -> None:
    with pytest.raises(
        ValueError,
        match="Period end must be on or after period start",
    ):
        make_payment(
            period_start=date(2026, 6, 30),
            period_end=date(2026, 5, 1),
        )


def test_obligation_payment_schema_validates_status() -> None:
    assert make_payment(status="paid").status == "paid"
    assert make_payment(status="cancelled").status == "cancelled"

    with pytest.raises(ValueError):
        make_payment(status="pending")
