import json
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.ai import llm_client
from app.schemas.ai_extraction import ExtractedTransaction


def _unknown_transaction(text: str) -> ExtractedTransaction:
    return ExtractedTransaction(
        type="unknown",
        amount=None,
        date=None,
        category=None,
        description=None,
        confidence=0,
        needs_confirmation=True,
        raw_text=text,
    )


def extract_transaction_from_text(text: str, today: date) -> ExtractedTransaction:
    try:
        raw_response = llm_client.extract_transaction_json(text=text, today=today)
        payload: dict[str, Any] = json.loads(raw_response)
        payload["raw_text"] = text
        return ExtractedTransaction.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError):
        return _unknown_transaction(text)
