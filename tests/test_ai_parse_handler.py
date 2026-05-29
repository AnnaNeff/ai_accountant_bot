import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.ai.llm_client import GroqConfigurationError
from app.bot.handlers import ai_parse
from app.schemas.ai_extraction import ExtractedTransaction


class FakeMessage:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def test_handle_ai_parse_without_text() -> None:
    message = FakeMessage("/ai_parse")

    asyncio.run(ai_parse.handle_ai_parse(message))  # type: ignore[arg-type]

    assert message.answers == [ai_parse.AI_PARSE_USAGE]


def test_handle_ai_parse_successful_income(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse получила 1500 шекелей за консультацию")

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

    asyncio.run(ai_parse.handle_ai_parse(message))  # type: ignore[arg-type]

    assert message.answers == [
        "AI parsed transaction:\n\n"
        "Type: income\n"
        "Amount: 1500.00 ILS\n"
        "Date: 2026-05-28\n"
        "Category: services\n"
        "Description: консультация\n"
        "Confidence: 0.87\n"
        "Needs confirmation: yes\n\n"
        "Not saved. This is preview only."
    ]


def test_handle_ai_parse_successful_expense(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse заплатила 86.40 за канцтовары")

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("86.40"),
            currency="ILS",
            date=date(2026, 5, 28),
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

    asyncio.run(ai_parse.handle_ai_parse(message))  # type: ignore[arg-type]

    assert message.answers == [
        "AI parsed transaction:\n\n"
        "Type: expense\n"
        "Amount: 86.40 ILS\n"
        "Date: 2026-05-28\n"
        "Category: office supplies\n"
        "Description: канцтовары\n"
        "Confidence: 0.91\n"
        "Needs confirmation: yes\n\n"
        "Not saved. This is preview only."
    ]


def test_handle_ai_parse_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse сколько у меня денег")

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

    asyncio.run(ai_parse.handle_ai_parse(message))  # type: ignore[arg-type]

    assert message.answers == ["AI could not confidently detect a transaction.\n\nNot saved."]


def test_handle_ai_parse_groq_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage("/ai_parse купила кофе за 18")

    def fake_extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
        raise GroqConfigurationError("GROQ_API_KEY is not configured.")

    monkeypatch.setattr(
        ai_parse,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(ai_parse.handle_ai_parse(message))  # type: ignore[arg-type]

    assert message.answers == ["AI is not configured. Set GROQ_API_KEY in .env."]
