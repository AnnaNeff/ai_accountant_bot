import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.bot.handlers import transactions
from app.bot.handlers.transactions import (
    SET_TRANSACTION_TAX_USAGE,
    TRANSACTION_USAGE,
    TransactionTaxUpdateCommand,
    format_last_transactions,
    format_transaction_details,
    parse_set_transaction_tax_command,
    parse_transaction_command,
    parse_transaction_id_command,
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


def make_detailed_transaction(**overrides: object) -> Transaction:
    data = {
        "id": 123,
        "user_id": 7,
        "type": "expense",
        "amount": Decimal("129.90"),
        "amount_total": Decimal("129.90"),
        "amount_net": None,
        "vat_amount": None,
        "vat_rate": None,
        "vat_included": None,
        "vat_relevant": False,
        "business_use_percent": Decimal("100.00"),
        "tax_deductible": None,
        "tax_category": None,
        "balance_impact_type": "business",
        "currency": "ILS",
        "date": date(2026, 6, 7),
        "category": "subscription",
        "description": "Telegram Premium Annual",
        "source": "document_ocr_ai",
        "status": "confirmed",
    }
    data.update(overrides)
    return Transaction(**data)


def test_format_transaction_details_shows_all_fields() -> None:
    assert format_transaction_details(make_detailed_transaction()) == (
        "Transaction details:\n\n"
        "ID: 123\n"
        "Date: 2026-06-07\n"
        "Type: expense\n"
        "Amount: 129.90 ILS\n"
        "Description: Telegram Premium Annual\n"
        "Category: subscription\n"
        "Source: document_ocr_ai\n"
        "Status: confirmed\n\n"
        "Tax/business fields:\n"
        "Amount total: 129.90\n"
        "Amount net: not set\n"
        "VAT amount: not set\n"
        "VAT rate: not set\n"
        "VAT included: not set\n"
        "VAT relevant: no\n"
        "Business use: 100.00%\n"
        "Tax deductible: not set\n"
        "Tax category: not set\n"
        "Balance impact type: business"
    )


def test_format_transaction_details_shows_updated_tax_fields() -> None:
    text = format_transaction_details(
        make_detailed_transaction(
            amount_net=Decimal("100.00"),
            vat_amount=Decimal("18.00"),
            vat_rate=Decimal("0.1800"),
            vat_included=True,
            vat_relevant=True,
            business_use_percent=Decimal("50.00"),
            tax_deductible=False,
            tax_category="home_office",
            balance_impact_type="personal",
        )
    )

    assert "Amount net: 100.00" in text
    assert "VAT amount: 18.00" in text
    assert "VAT rate: 0.1800" in text
    assert "VAT included: yes" in text
    assert "VAT relevant: yes" in text
    assert "Business use: 50.00%" in text
    assert "Tax deductible: no" in text
    assert "Tax category: home_office" in text
    assert "Balance impact type: personal" in text


def test_parse_transaction_id_command_validates_format() -> None:
    assert parse_transaction_id_command("/transaction") == TRANSACTION_USAGE
    assert parse_transaction_id_command("/transaction abc") == TRANSACTION_USAGE
    assert parse_transaction_id_command("/transaction 0") == TRANSACTION_USAGE
    assert parse_transaction_id_command("/transaction 123") == 123


def test_set_transaction_tax_validates_format_and_field() -> None:
    assert (
        parse_set_transaction_tax_command("/set_transaction_tax")
        == SET_TRANSACTION_TAX_USAGE
    )
    assert (
        parse_set_transaction_tax_command(
            "/set_transaction_tax 123 source document_ocr_ai"
        )
        == "Unsupported tax field."
    )
    assert (
        parse_set_transaction_tax_command("/set_transaction_tax 123 amount 1")
        == "Unsupported tax field."
    )
    assert (
        parse_set_transaction_tax_command("/set_transaction_tax 123 status pending")
        == "Unsupported tax field."
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("yes", True),
        ("1", True),
        ("false", False),
        ("no", False),
        ("0", False),
    ],
)
def test_set_transaction_tax_parses_boolean_values(
    raw_value: str,
    expected: bool,
) -> None:
    command = parse_set_transaction_tax_command(
        f"/set_transaction_tax 123 vat_relevant {raw_value}"
    )

    assert isinstance(command, TransactionTaxUpdateCommand)
    assert command.value is expected
    assert command.display_value == ("true" if expected else "false")


def test_set_transaction_tax_rejects_invalid_boolean() -> None:
    assert (
        parse_set_transaction_tax_command(
            "/set_transaction_tax 123 vat_relevant maybe"
        )
        == "Invalid value for this field."
    )


def test_set_transaction_tax_validates_vat_rate() -> None:
    command = parse_set_transaction_tax_command(
        "/set_transaction_tax 123 vat_rate 0.18"
    )
    assert isinstance(command, TransactionTaxUpdateCommand)
    assert command.value == Decimal("0.18")
    assert (
        parse_set_transaction_tax_command(
            "/set_transaction_tax 123 vat_rate 1.01"
        )
        == "Invalid value for this field."
    )


def test_set_transaction_tax_validates_business_use_percent() -> None:
    command = parse_set_transaction_tax_command(
        "/set_transaction_tax 123 business_use_percent 50"
    )
    assert isinstance(command, TransactionTaxUpdateCommand)
    assert command.value == Decimal("50")
    assert (
        parse_set_transaction_tax_command(
            "/set_transaction_tax 123 business_use_percent 100.01"
        )
        == "Invalid value for this field."
    )


@pytest.mark.parametrize("field", ["amount_total", "amount_net", "vat_amount"])
def test_set_transaction_tax_accepts_non_negative_amount_fields(field: str) -> None:
    command = parse_set_transaction_tax_command(
        f"/set_transaction_tax 123 {field} 0"
    )
    assert isinstance(command, TransactionTaxUpdateCommand)
    assert command.value == Decimal("0")
    assert (
        parse_set_transaction_tax_command(
            f"/set_transaction_tax 123 {field} -0.01"
        )
        == "Invalid value for this field."
    )


def test_set_transaction_tax_sets_and_clears_tax_category() -> None:
    command = parse_set_transaction_tax_command(
        "/set_transaction_tax 123 tax_category home_office"
    )
    assert isinstance(command, TransactionTaxUpdateCommand)
    assert command.value == "home_office"

    cleared = parse_set_transaction_tax_command(
        "/set_transaction_tax 123 tax_category null"
    )
    assert isinstance(cleared, TransactionTaxUpdateCommand)
    assert cleared.value is None
    assert cleared.display_value == "null"


def test_set_transaction_tax_validates_balance_impact_type() -> None:
    for value in (
        "business",
        "personal",
        "tax_payment",
        "transfer",
        "reserve_only",
    ):
        command = parse_set_transaction_tax_command(
            f"/set_transaction_tax 123 balance_impact_type {value}"
        )
        assert isinstance(command, TransactionTaxUpdateCommand)
        assert command.value == value

    assert (
        parse_set_transaction_tax_command(
            "/set_transaction_tax 123 balance_impact_type unknown"
        )
        == "Invalid value for this field."
    )


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


def setup_transaction_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    monkeypatch.setattr(
        transactions,
        "get_async_session_factory",
        lambda: FakeSessionContext,
    )
    monkeypatch.setattr(
        transactions,
        "get_or_create_user",
        fake_get_or_create_user,
    )


def test_transaction_handler_shows_current_user_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/transaction 123")
    setup_transaction_handlers(monkeypatch)

    async def fake_get_transaction_by_id(
        session: object,
        **kwargs: Any,
    ) -> Transaction:
        assert kwargs == {"user_id": 7, "transaction_id": 123}
        return make_detailed_transaction()

    monkeypatch.setattr(
        transactions,
        "get_transaction_by_id",
        fake_get_transaction_by_id,
    )

    asyncio.run(transactions.handle_transaction(message))  # type: ignore[arg-type]

    assert message.answers == [format_transaction_details(make_detailed_transaction())]


def test_transaction_handler_unknown_id_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/transaction 999")
    setup_transaction_handlers(monkeypatch)

    async def fake_get_transaction_by_id(
        session: object,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        transactions,
        "get_transaction_by_id",
        fake_get_transaction_by_id,
    )

    asyncio.run(transactions.handle_transaction(message))  # type: ignore[arg-type]

    assert message.answers == ["Transaction not found."]


def test_set_transaction_tax_handler_updates_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/set_transaction_tax 123 vat_relevant true")
    setup_transaction_handlers(monkeypatch)
    transaction = make_detailed_transaction(vat_relevant=True)

    async def fake_update_transaction_tax_field(
        session: object,
        **kwargs: Any,
    ) -> Transaction:
        assert kwargs == {
            "user_id": 7,
            "transaction_id": 123,
            "field": "vat_relevant",
            "value": True,
        }
        return transaction

    monkeypatch.setattr(
        transactions,
        "update_transaction_tax_field",
        fake_update_transaction_tax_field,
    )

    asyncio.run(
        transactions.handle_set_transaction_tax(message)  # type: ignore[arg-type]
    )

    assert message.answers == [
        "Transaction tax field updated.\n\n"
        "Transaction ID: 123\n"
        "Field: vat_relevant\n"
        "Value: true"
    ]


def test_set_transaction_tax_handler_unknown_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/set_transaction_tax 999 vat_relevant true")
    setup_transaction_handlers(monkeypatch)

    async def fake_update_transaction_tax_field(
        session: object,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        transactions,
        "update_transaction_tax_field",
        fake_update_transaction_tax_field,
    )

    asyncio.run(
        transactions.handle_set_transaction_tax(message)  # type: ignore[arg-type]
    )

    assert message.answers == ["Transaction not found."]
