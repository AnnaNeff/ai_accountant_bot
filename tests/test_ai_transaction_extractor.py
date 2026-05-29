import sys
from datetime import date
from decimal import Decimal
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import ValidationError

from app.ai import transaction_extractor
from app.ai.llm_client import GroqConfigurationError, extract_transaction_json
from app.ai.transaction_extractor import extract_transaction_from_text
from app.core.config import Settings
from app.schemas.ai_extraction import ExtractedTransaction


TODAY = date(2026, 5, 29)


def mock_llm(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    def fake_extract_transaction_json(text: str, today: date) -> str:
        return response

    monkeypatch.setattr(
        transaction_extractor.llm_client,
        "extract_transaction_json",
        fake_extract_transaction_json,
    )


def test_extracts_income(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_llm(
        monkeypatch,
        """
        {
          "type": "income",
          "amount": 1500,
          "currency": "ILS",
          "date": "2026-05-29",
          "category": "consulting",
          "description": "consultation payment",
          "confidence": 0.92,
          "needs_confirmation": true,
          "raw_text": "ignored"
        }
        """,
    )

    result = extract_transaction_from_text("получила 1500 шекелей за консультацию", TODAY)

    assert result.type == "income"
    assert result.amount == Decimal("1500")
    assert result.currency == "ILS"
    assert result.date == TODAY
    assert result.category == "consulting"
    assert result.confidence == 0.92
    assert result.needs_confirmation is True
    assert result.raw_text == "получила 1500 шекелей за консультацию"


def test_extracts_expense(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_llm(
        monkeypatch,
        """
        {
          "type": "expense",
          "amount": 86.40,
          "currency": "ILS",
          "date": null,
          "category": "office supplies",
          "description": "stationery",
          "confidence": 0.88,
          "needs_confirmation": true,
          "raw_text": "ignored"
        }
        """,
    )

    result = extract_transaction_from_text("заплатила 86.40 за канцтовары", TODAY)

    assert result.type == "expense"
    assert result.amount == Decimal("86.40")
    assert result.date is None
    assert result.category == "office supplies"
    assert result.description == "stationery"


def test_extracts_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_llm(
        monkeypatch,
        """
        {
          "type": "unknown",
          "amount": null,
          "currency": "ILS",
          "date": null,
          "category": null,
          "description": null,
          "confidence": 0.1,
          "needs_confirmation": true,
          "raw_text": "ignored"
        }
        """,
    )

    result = extract_transaction_from_text("сколько у меня денег", TODAY)

    assert result.type == "unknown"
    assert result.amount is None
    assert result.confidence == 0.1
    assert result.needs_confirmation is True


def test_invalid_json_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_llm(monkeypatch, "not json")

    result = extract_transaction_from_text("купила кофе за 18", TODAY)

    assert result.type == "unknown"
    assert result.amount is None
    assert result.confidence == 0
    assert result.needs_confirmation is True
    assert result.raw_text == "купила кофе за 18"


def test_non_positive_amount_is_not_valid_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_llm(
        monkeypatch,
        """
        {
          "type": "expense",
          "amount": 0,
          "currency": "ILS",
          "date": null,
          "category": "coffee",
          "description": "coffee",
          "confidence": 0.9,
          "needs_confirmation": true,
          "raw_text": "ignored"
        }
        """,
    )

    result = extract_transaction_from_text("купила кофе за 0", TODAY)

    assert result.type == "unknown"
    assert result.amount is None
    assert result.confidence == 0


def test_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        ExtractedTransaction(
            type="expense",
            amount=Decimal("18"),
            confidence=1.1,
            needs_confirmation=True,
            raw_text="купила кофе за 18",
        )


def test_llm_client_requires_groq_api_key() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        GROQ_API_KEY="",
    )

    with pytest.raises(GroqConfigurationError, match="GROQ_API_KEY"):
        extract_transaction_json("купила кофе за 18", TODAY, settings=settings)


def test_llm_client_uses_groq_json_mode_without_real_api_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            calls["create"] = kwargs
            message = SimpleNamespace(content='{"type":"unknown","confidence":0}')
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            calls["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_openai_module = ModuleType("openai")
    fake_openai_module.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_openai_module)

    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        GROQ_API_KEY="test-groq-key",
        GROQ_MODEL="llama-3.1-8b-instant",
    )

    result = extract_transaction_json("сколько у меня денег", TODAY, settings=settings)

    assert result == '{"type":"unknown","confidence":0}'
    assert calls["client"] == {
        "api_key": "test-groq-key",
        "base_url": "https://api.groq.com/openai/v1",
    }
    create_kwargs = calls["create"]
    assert isinstance(create_kwargs, dict)
    assert create_kwargs["model"] == "llama-3.1-8b-instant"
    assert create_kwargs["response_format"] == {"type": "json_object"}
