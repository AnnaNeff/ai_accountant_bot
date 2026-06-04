import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.ai.llm_client import GroqConfigurationError
from app.bot.handlers import ai_parse
from app.bot.states import AiTransactionConfirmation
from app.schemas.ai_extraction import ExtractedTransaction


class FakeMessage:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.answers: list[dict[str, Any]] = []
        self.edits: list[dict[str, Any]] = []
        self.edit_text_error: Exception | None = None

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        if self.edit_text_error is not None:
            raise self.edit_text_error
        self.edits.append({"text": text, **kwargs})


class FakeState:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data or {}
        self.state: object | None = None
        self.cleared = False

    async def update_data(self, data: dict[str, Any]) -> None:
        self.data.update(data)

    async def set_state(self, state: object) -> None:
        self.state = state

    async def get_data(self) -> dict[str, Any]:
        return self.data

    async def clear(self) -> None:
        self.data = {}
        self.state = None
        self.cleared = True


class FakeCallback:
    def __init__(self, state_data: dict[str, Any] | None = None) -> None:
        self.message = FakeMessage(None)
        self.from_user = SimpleNamespace(id=12345, full_name="Test User")
        self.answers: list[dict[str, Any]] = []
        self.state = FakeState(state_data)

    async def answer(self, **kwargs: Any) -> None:
        self.answers.append(kwargs)


class FakeSessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def pending_ai_transaction(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": "income",
        "amount": "1500",
        "currency": "ILS",
        "date": "2026-05-28",
        "category": "services",
        "description": "консультация",
        "confidence": 0.87,
        "needs_confirmation": True,
        "raw_text": "получила 1500 за консультацию",
    }
    data.update(overrides)
    return {ai_parse.AI_TRANSACTION_STATE_KEY: data}


def test_handle_ai_parse_without_text() -> None:
    message = FakeMessage("/ai_parse")
    state = FakeState()

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [{"text": ai_parse.AI_PARSE_USAGE}]
    assert state.data == {}
    assert state.state is None


def test_handle_ai_parse_successful_parse_shows_inline_buttons_without_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/ai_parse получила 1500 шекелей за консультацию")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        assert text == "получила 1500 шекелей за консультацию"
        return ExtractedTransaction(
            type="income",
            amount=Decimal("1500"),
            currency="ILS",
            date=date(2026, 5, 28),
            category="services",
            description="консультация",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        {
            "text": "AI parsed transaction:\n\n"
            "Type: income\n"
            "Amount: 1500.00 ILS\n"
            "Date: 2026-05-28\n"
            "Category: services\n"
            "Description: консультация\n"
            "\n"
            "Save this transaction?",
            "reply_markup": message.answers[0]["reply_markup"],
        }
    ]
    assert "Confidence:" not in message.answers[0]["text"]
    keyboard = message.answers[0]["reply_markup"]
    buttons = keyboard.inline_keyboard[0]
    assert buttons[0].text == "Save transaction"
    assert buttons[0].callback_data == "ai_transaction:save"
    assert buttons[1].text == "Cancel"
    assert buttons[1].callback_data == "ai_transaction:cancel"


def test_handle_ai_parse_successful_parse_logs_confidence(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = FakeMessage("/ai_parse получила 1500 шекелей за консультацию")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="income",
            amount=Decimal("1500"),
            currency="ILS",
            date=date(2026, 5, 28),
            category="services",
            description="консультация",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    with caplog.at_level("INFO", logger=ai_parse.logger.name):
        asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert "confidence=0.87" in caplog.text
    assert "Confidence:" not in message.answers[0]["text"]


def test_handle_ai_parse_successful_parse_does_not_create_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/ai_parse получила 1500 шекелей за консультацию")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="income",
            amount=Decimal("1500"),
            currency="ILS",
            date=date(2026, 5, 28),
            category="services",
            description="консультация",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    async def fail_create_transaction(**kwargs: Any) -> None:
        raise AssertionError("create_transaction should not be called during parse")

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )
    monkeypatch.setattr(ai_parse, "create_transaction", fail_create_transaction)

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert state.state == AiTransactionConfirmation.waiting_for_confirmation
    assert "reply_markup" in message.answers[0]


def test_handle_ai_parse_successful_parse_saves_data_in_fsm_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/ai_parse заплатила 86.40 за канцтовары")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("86.40"),
            currency="ILS",
            date=None,
            category="office supplies",
            description="канцтовары",
            confidence=0.91,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert state.state == AiTransactionConfirmation.waiting_for_confirmation
    assert state.data == {
        ai_parse.AI_TRANSACTION_STATE_KEY: {
            "type": "expense",
            "amount": "86.40",
            "currency": "ILS",
            "date": date.today().isoformat(),
            "category": "office supplies",
            "description": "канцтовары",
            "confidence": 0.91,
            "needs_confirmation": True,
            "raw_text": "заплатила 86.40 за канцтовары",
        }
    }
    assert f"Date: {date.today().isoformat()}" in message.answers[0]["text"]


def test_handle_ai_parse_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse сколько у меня денег")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="unknown",
            amount=None,
            currency="ILS",
            date=None,
            category=None,
            description=None,
            confidence=0,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        {"text": "AI could not confidently detect a transaction.\n\nNot saved."}
    ]
    assert "reply_markup" not in message.answers[0]
    assert state.data == {}
    assert state.state is None


def test_handle_ai_parse_missing_amount_does_not_show_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage("/ai_parse получила оплату")
    state = FakeState(pending_ai_transaction())

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="income",
            amount=None,
            currency="ILS",
            date=date(2026, 5, 28),
            category="services",
            description="оплата",
            confidence=0.82,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        {"text": "AI could not confidently detect a transaction.\n\nNot saved."}
    ]
    assert "reply_markup" not in message.answers[0]
    assert state.cleared is True
    assert state.data == {}
    assert state.state is None


def test_handle_ai_parse_low_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse получила около 20")
    state = FakeState(pending_ai_transaction())

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="income",
            amount=Decimal("20"),
            currency="ILS",
            date=date(2026, 5, 28),
            category=None,
            description="получила около 20",
            confidence=0.49,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        {"text": "AI confidence is too low to create a transaction.\n\nNot saved."}
    ]
    assert "reply_markup" not in message.answers[0]
    assert state.cleared is True
    assert state.data == {}
    assert state.state is None


def test_handle_ai_parse_groq_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse купила кофе за 18")
    state = FakeState()

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        raise GroqConfigurationError("GROQ_API_KEY is not configured.")

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message, state))  # type: ignore[arg-type]

    assert message.answers == [{"text": "AI is not configured. Set GROQ_API_KEY in .env."}]
    assert state.data == {}
    assert state.state is None


def test_handle_ai_transaction_save_creates_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())
    created: dict[str, Any] = {}

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        assert telegram_user_id == 12345
        assert name == "Test User"
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        created.update(kwargs)
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    transaction_data = created["data"]
    assert created["user_id"] == 77
    assert transaction_data.type == "income"
    assert transaction_data.amount == Decimal("1500")
    assert transaction_data.amount_total == Decimal("1500")
    assert transaction_data.vat_relevant is False
    assert transaction_data.business_use_percent == Decimal("100.00")
    assert transaction_data.balance_impact_type == "business"
    assert transaction_data.currency == "ILS"
    assert transaction_data.date == date(2026, 5, 28)
    assert transaction_data.category == "services"
    assert transaction_data.description == "консультация"
    assert callback.message.edits == [
        {"text": "Transaction saved.", "reply_markup": None}
    ]


def test_handle_ai_transaction_save_creates_transaction_with_ai_text_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())
    created: dict[str, Any] = {}

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        created.update(kwargs)
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert created["source"] == "ai_text"
    assert created["status"] == "confirmed"


def test_handle_ai_transaction_save_clears_fsm_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert callback.state.cleared is True
    assert callback.state.data == {}


def test_handle_ai_transaction_save_removes_inline_keyboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.edits == [
        {"text": "Transaction saved.", "reply_markup": None}
    ]


def test_handle_ai_transaction_save_falls_back_to_answer_when_edit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())
    callback.message.edit_text_error = TelegramBadRequest(None, "message can't be edited")  # type: ignore[arg-type]

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.answers == [{"text": "Transaction saved."}]


def test_handle_ai_transaction_repeated_save_does_not_create_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())
    created_count = 0

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=77)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        nonlocal created_count
        created_count += 1
        return SimpleNamespace(id=100)

    monkeypatch.setattr(ai_parse, "get_async_session_factory", lambda: FakeSessionContext)
    monkeypatch.setattr(ai_parse, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(ai_parse, "create_transaction", fake_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]
    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert created_count == 1
    assert callback.message.answers == [
        {"text": "No pending AI transaction to save."}
    ]


def test_handle_ai_transaction_cancel_does_not_create_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_ai_transaction())

    async def fail_create_transaction(**kwargs: Any) -> None:
        raise AssertionError("create_transaction should not be called")

    monkeypatch.setattr(ai_parse, "create_transaction", fail_create_transaction)

    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.edits == [
        {"text": "AI transaction cancelled. Not saved.", "reply_markup": None}
    ]


def test_handle_ai_transaction_cancel_clears_fsm_state() -> None:
    callback = FakeCallback(pending_ai_transaction())

    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]

    assert callback.state.cleared is True
    assert callback.state.data == {}


def test_handle_ai_transaction_cancel_removes_inline_keyboard() -> None:
    callback = FakeCallback(pending_ai_transaction())

    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.edits == [
        {"text": "AI transaction cancelled. Not saved.", "reply_markup": None}
    ]


def test_handle_ai_transaction_repeated_cancel_does_not_fail() -> None:
    callback = FakeCallback(pending_ai_transaction())

    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]
    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.edits == [
        {"text": "AI transaction cancelled. Not saved.", "reply_markup": None}
    ]
    assert callback.message.answers == [
        {"text": "No pending AI transaction to cancel."}
    ]


def test_handle_ai_transaction_save_without_pending_state_returns_message() -> None:
    callback = FakeCallback()

    asyncio.run(ai_parse.handle_ai_transaction_save(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.answers == [
        {"text": "No pending AI transaction to save."}
    ]
    assert callback.state.cleared is False


def test_handle_ai_transaction_cancel_without_pending_state_returns_message() -> None:
    callback = FakeCallback()

    asyncio.run(ai_parse.handle_ai_transaction_cancel(callback, callback.state))  # type: ignore[arg-type]

    assert callback.message.answers == [
        {"text": "No pending AI transaction to cancel."}
    ]
    assert callback.state.cleared is False
