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
