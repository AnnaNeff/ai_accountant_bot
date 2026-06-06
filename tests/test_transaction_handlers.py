from datetime import date
from decimal import Decimal

import pytest

from app.bot.handlers.transactions import (
    format_last_transactions,
    parse_transaction_command,
)
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate


def test_parse_transaction_command_uses_manual_entry_defaults() -> None:
    result = parse_transaction_command("/income 1500 consulting payment", "income")

    assert isinstance(result, TransactionCreate)
    assert result.type == "income"
    assert result.amount == Decimal("1500")
    assert result.amount_total == Decimal("1500")
    assert result.vat_relevant is False
    assert result.business_use_percent == Decimal("100.00")
    assert result.balance_impact_type == "business"
    assert result.currency == "ILS"
    assert result.category is None
    assert result.description == "consulting payment"


def test_parse_transaction_command_rejects_missing_or_invalid_amount() -> None:
    assert parse_transaction_command("/income", "income") == (
        "Use format: /income 1500 consulting payment"
    )
    assert parse_transaction_command("/expense zero supplies", "expense") == (
        "Amount must be a positive number."
    )
    assert parse_transaction_command("/expense 0 supplies", "expense") == (
        "Amount must be a positive number."
    )


def test_transaction_create_rejects_invalid_amount() -> None:
    with pytest.raises(ValueError, match="Amount must be a positive number"):
        TransactionCreate(
            type="expense",
            amount=Decimal("-1"),
            date=date(2026, 5, 8),
        )


def test_transaction_create_defaults_new_tax_fields_safely() -> None:
    transaction = TransactionCreate(
        type="expense",
        amount=Decimal("86.40"),
        date=date(2026, 5, 8),
    )

    assert transaction.amount_total == Decimal("86.40")
    assert transaction.amount_net is None
    assert transaction.vat_amount is None
    assert transaction.vat_rate is None
    assert transaction.vat_included is None
    assert transaction.vat_relevant is False
    assert transaction.business_use_percent == Decimal("100.00")
    assert transaction.tax_deductible is None
    assert transaction.tax_category is None
    assert transaction.balance_impact_type == "business"


def test_transaction_create_validates_business_use_percent() -> None:
    with pytest.raises(ValueError, match="Business use percent must be between 0 and 100"):
        TransactionCreate(
            type="expense",
            amount=Decimal("86.40"),
            date=date(2026, 5, 8),
            business_use_percent=Decimal("100.01"),
        )


def test_transaction_create_validates_balance_impact_type() -> None:
    with pytest.raises(ValueError):
        TransactionCreate(
            type="expense",
            amount=Decimal("86.40"),
            date=date(2026, 5, 8),
            balance_impact_type="invalid",  # type: ignore[arg-type]
        )


def test_format_last_transactions() -> None:
    transaction = Transaction(
        user_id=1,
        type="expense",
        amount=Decimal("86.40"),
        currency="ILS",
        date=date(2026, 5, 8),
        description="office supplies",
        source="manual",
        status="confirmed",
    )

    assert format_last_transactions([transaction]) == (
        "Last transactions:\n\n"
        "1. 2026-05-08 | expense | 86.40 ILS | office supplies"
    )
    assert format_last_transactions([]) == "No transactions yet."


def test_format_last_transactions_shows_obligation_manual_payment() -> None:
    transaction = Transaction(
        user_id=1,
        type="expense",
        amount=Decimal("650.00"),
        currency="ILS",
        date=date(2026, 6, 6),
        description="Bituach Leumi payment",
        source="obligation_manual_payment",
        status="confirmed",
    )

    assert format_last_transactions([transaction]) == (
        "Last transactions:\n\n"
        "1. 2026-06-06 | expense | 650.00 ILS | Bituach Leumi payment"
    )
