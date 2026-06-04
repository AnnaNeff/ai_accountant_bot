import asyncio
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.ai.llm_client import GroqConfigurationError
from app.bot import keyboards
from app.bot.handlers import documents
from app.bot.states import DocumentTransactionConfirmation
from app.schemas.ai_extraction import ExtractedTransaction
from app.schemas.document import DocumentCreate


class FakeBot:
    def __init__(
        self,
        content: bytes = b"document-bytes",
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.downloads: list[dict[str, Any]] = []

    async def download(self, file: str, destination: Path) -> None:
        self.downloads.append({"file": file, "destination": destination})
        if self.error is not None:
            raise self.error
        destination.write_bytes(self.content)


class FakeMessage:
    def __init__(
        self,
        photo: list[Any] | None = None,
        bot: FakeBot | None = None,
        text: str | None = None,
    ) -> None:
        self.from_user = SimpleNamespace(id=12345, full_name="Test User")
        self.photo = photo or []
        self.bot = bot or FakeBot()
        self.text = text
        self.answers: list[str] = []
        self.answer_kwargs: list[dict[str, Any]] = []
        self.edits: list[dict[str, Any]] = []
        self.edit_text_error: Exception | None = None

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)
        self.answer_kwargs.append(kwargs)

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        if self.edit_text_error is not None:
            raise self.edit_text_error
        self.edits.append({"text": text, **kwargs})


class FakeSessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def fake_session_factory() -> FakeSessionContext:
    return FakeSessionContext()


class FakeState:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = data or {}
        self.state: Any = None
        self.clear_calls = 0

    async def clear(self) -> None:
        self.data = {}
        self.state = None
        self.clear_calls += 1

    async def update_data(self, data: dict[str, Any]) -> None:
        self.data.update(data)

    async def set_state(self, state: Any) -> None:
        self.state = state

    async def get_data(self) -> dict[str, Any]:
        return self.data


class FakeCallback:
    def __init__(self, state_data: dict[str, Any] | None = None) -> None:
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=12345, full_name="Test User")
        self.answers: list[dict[str, Any]] = []
        self.state = FakeState(state_data)

    async def answer(self, **kwargs: Any) -> None:
        self.answers.append(kwargs)


class FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 5, 30)


def photo(file_id: str = "telegram-file-id", file_size: int | None = 14) -> Any:
    return SimpleNamespace(
        file_id=file_id,
        file_size=file_size,
        width=1280,
        height=960,
    )


def pending_document_transaction(**overrides: Any) -> dict[str, Any]:
    transaction: dict[str, Any] = {
        "type": "expense",
        "amount": "129.90",
        "currency": "ILS",
        "date": "2025-09-16",
        "category": "subscription",
        "description": "Telegram Premium Annual",
        "confidence": 0.87,
        "needs_confirmation": True,
        "raw_text": "Telegram Premium Annual 129.90 ILS",
    }
    transaction.update(overrides.pop("transaction", {}))
    pending: dict[str, Any] = {
        "document_id": 4,
        "transaction": transaction,
    }
    pending.update(overrides)
    return {documents.DOCUMENT_TRANSACTION_STATE_KEY: pending}


def test_photo_handler_creates_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created: dict[str, Any] = {}
    message = FakeMessage(photo=[photo()], bot=FakeBot())

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_create_document(
        session: object,
        user_id: int,
        data: DocumentCreate,
    ) -> Any:
        created["user_id"] = user_id
        created["data"] = data
        return SimpleNamespace(id=123, status="uploaded")

    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(document_storage_path=str(tmp_path)),
    )
    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "create_document", fake_create_document)

    asyncio.run(documents.handle_photo_document(message))  # type: ignore[arg-type]

    document_data = created["data"]
    saved_path = Path(document_data.local_path)

    assert created["user_id"] == 7
    assert saved_path.read_bytes() == b"document-bytes"
    assert saved_path.relative_to(tmp_path).parts[0] == "7"
    assert document_data.transaction_id is None
    assert document_data.telegram_file_id == "telegram-file-id"
    assert document_data.mime_type == "image/jpeg"
    assert document_data.file_size_bytes == 14
    assert document_data.status == "uploaded"
    assert message.answers == [
        "Document saved.\n\n"
        "ID: 123\n"
        "Status: uploaded\n\n"
        "OCR is available. Use /ocr_document <document_id> to extract text."
    ]


def test_old_photo_ocr_placeholder_text_is_not_used() -> None:
    source = Path(documents.__file__).read_text()

    assert "OCR is not implemented yet." not in source


def test_photo_handler_does_not_create_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    message = FakeMessage(photo=[photo()], bot=FakeBot())

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_create_document(
        session: object,
        user_id: int,
        data: DocumentCreate,
    ) -> Any:
        assert data.transaction_id is None
        return SimpleNamespace(id=123, status="uploaded")

    async def fail_create_transaction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Photo handler must not create transactions")

    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(document_storage_path=str(tmp_path)),
    )
    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "create_document", fake_create_document)
    monkeypatch.setattr(
        "app.services.transaction_service.create_transaction",
        fail_create_transaction,
    )

    asyncio.run(documents.handle_photo_document(message))  # type: ignore[arg-type]

    assert message.answers[0].startswith("Document saved.")


def test_handle_documents_shows_last_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_last_documents(
        session: object,
        user_id: int,
        limit: int,
    ) -> list[Any]:
        assert user_id == 7
        assert limit == 10
        return [
            SimpleNamespace(
                id=12,
                status="uploaded",
                ocr_status="completed",
                transaction_id=45,
                created_at=datetime(2026, 5, 30),
            ),
            SimpleNamespace(
                id=11,
                status="uploaded",
                ocr_status="not_started",
                transaction_id=None,
                created_at=datetime(2026, 5, 29),
            ),
        ]

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_last_documents", fake_get_last_documents)

    asyncio.run(documents.handle_documents(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Documents:\n\n"
        "1. ID 12 | uploaded | OCR completed | transaction 45 | 2026-05-30\n"
        "2. ID 11 | uploaded | OCR not_started | not linked | 2026-05-29"
    ]


def test_handle_document_shows_details(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage(text="/document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> Any:
        assert user_id == 7
        assert document_id == 12
        return SimpleNamespace(
            id=12,
            status="uploaded",
            ocr_status="completed",
            ocr_processed_at=datetime(2026, 5, 30, 12, 0),
            ocr_text="Super-Pharm\n86.40 ILS",
            transaction_id=None,
            created_at=datetime(2026, 5, 30),
            file_size_bytes=123456,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)

    asyncio.run(documents.handle_document(message))  # type: ignore[arg-type]

    assert message.answers == [
        "Document details:\n\n"
        "ID: 12\n"
        "Status: uploaded\n"
        "OCR status: completed\n"
        "OCR processed at: 2026-05-30T12:00:00\n"
        "Created at: 2026-05-30\n"
        "Transaction ID: not linked\n"
        "File size: 123456 bytes\n\n"
        "OCR text preview:\n"
        "Super-Pharm\n"
        "86.40 ILS"
    ]


def test_handle_ocr_document_validates_format() -> None:
    message = FakeMessage(text="/ocr_document")

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert message.answers == ["Use format: /ocr_document 12"]


def test_handle_ocr_document_shows_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage(text="/ocr_document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> None:
        assert user_id == 7
        assert document_id == 12
        return None

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert message.answers == ["Document not found."]


def test_handle_ocr_document_saves_successful_ocr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-image")
    message = FakeMessage(text="/ocr_document 12")
    saved: dict[str, Any] = {}

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> Any:
        return SimpleNamespace(id=document_id, user_id=user_id, local_path=str(image_path))

    def fake_extract_text_from_image(path: Path, languages: str) -> str:
        assert path == image_path
        assert languages == "eng"
        return "Super-Pharm\n86.40 ILS"

    async def fake_save_document_ocr_result(**kwargs: Any) -> Any:
        saved.update(kwargs)
        return SimpleNamespace(id=kwargs["document_id"], ocr_status="completed")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "extract_text_from_image", fake_extract_text_from_image)
    monkeypatch.setattr(documents, "save_document_ocr_result", fake_save_document_ocr_result)

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert saved["user_id"] == 7
    assert saved["document_id"] == 12
    assert saved["ocr_text"] == "Super-Pharm\n86.40 ILS"
    assert saved["success"] is True
    assert message.answers == [
        "OCR completed.\n\n"
        "Document ID: 12\n\n"
        "Recognized text:\n"
        "Super-Pharm\n"
        "86.40 ILS"
    ]


def test_handle_ocr_document_empty_text_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-image")
    message = FakeMessage(text="/ocr_document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=12, local_path=str(image_path))

    async def fake_save_document_ocr_result(**kwargs: Any) -> Any:
        assert kwargs["ocr_text"] == ""
        assert kwargs["success"] is True
        return SimpleNamespace(id=12, ocr_status="completed")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "extract_text_from_image", lambda path, languages: "")
    monkeypatch.setattr(documents, "save_document_ocr_result", fake_save_document_ocr_result)

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert message.answers == [
        "OCR completed, but no text was recognized.\n\n"
        "Document ID: 12"
    ]


def test_handle_ocr_document_exception_saves_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-image")
    message = FakeMessage(text="/ocr_document 12")
    saved: dict[str, Any] = {}

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=12, local_path=str(image_path))

    def fail_extract_text_from_image(path: Path, languages: str) -> str:
        raise RuntimeError("tesseract failed")

    async def fake_save_document_ocr_result(**kwargs: Any) -> Any:
        saved.update(kwargs)
        return SimpleNamespace(id=12, ocr_status="failed")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "extract_text_from_image", fail_extract_text_from_image)
    monkeypatch.setattr(documents, "save_document_ocr_result", fake_save_document_ocr_result)

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert saved["success"] is False
    assert saved["ocr_text"] == ""
    assert saved["error_message"] == "tesseract failed"
    assert message.answers == ["OCR failed. Please check the document image and OCR setup."]


def test_handle_ocr_document_missing_file_saves_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.jpg"
    message = FakeMessage(text="/ocr_document 12")
    saved: dict[str, Any] = {}

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=12, local_path=str(missing_path))

    async def fake_save_document_ocr_result(**kwargs: Any) -> Any:
        saved.update(kwargs)
        return SimpleNamespace(id=12, ocr_status="failed")

    def fail_extract_text_from_image(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("OCR must not run when the local file is missing")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "extract_text_from_image", fail_extract_text_from_image)
    monkeypatch.setattr(documents, "save_document_ocr_result", fake_save_document_ocr_result)

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert saved["success"] is False
    assert saved["ocr_text"] == ""
    assert str(missing_path) in saved["error_message"]
    assert message.answers == ["Document file not found."]


def test_handle_ocr_document_does_not_create_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-image")
    message = FakeMessage(text="/ocr_document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=12, local_path=str(image_path))

    async def fake_save_document_ocr_result(**kwargs: Any) -> Any:
        return SimpleNamespace(id=12, ocr_status="completed")

    async def fail_create_transaction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("OCR handler must not create transactions")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(ocr_languages="eng"))
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "extract_text_from_image", lambda path, languages: "text")
    monkeypatch.setattr(documents, "save_document_ocr_result", fake_save_document_ocr_result)
    monkeypatch.setattr(
        "app.services.transaction_service.create_transaction",
        fail_create_transaction,
    )

    asyncio.run(documents.handle_ocr_document(message))  # type: ignore[arg-type]

    assert message.answers[0].startswith("OCR completed.")


def test_handle_parse_document_validates_format() -> None:
    message = FakeMessage(text="/parse_document")

    asyncio.run(documents.handle_parse_document(message, FakeState()))  # type: ignore[arg-type]

    assert message.answers == ["Use format: /parse_document 12"]


def test_handle_parse_document_shows_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage(text="/parse_document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> None:
        assert user_id == 7
        assert document_id == 12
        return None

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)

    asyncio.run(documents.handle_parse_document(message, FakeState()))  # type: ignore[arg-type]

    assert message.answers == ["Document not found."]


def test_handle_parse_document_requires_completed_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 12")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=12, ocr_status="not_started", ocr_text=None)

    def fail_extract_transaction_from_text(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("AI extractor must not run without completed OCR text")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fail_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, FakeState()))  # type: ignore[arg-type]

    assert message.answers == [
        "Document has no completed OCR text. Run /ocr_document first."
    ]


def test_handle_parse_document_successful_ai_parse_shows_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(
            id=4,
            ocr_status="completed",
            ocr_text="Telegram Premium Annual 129.90 ILS 2025-09-16",
            transaction_id=None,
        )

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        assert text == "Telegram Premium Annual 129.90 ILS 2025-09-16"
        assert today == date(2026, 5, 30)
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=date(2025, 9, 16),
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(documents, "date", FixedDate)
    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        "AI parsed document transaction:\n\n"
        "Document ID: 4\n"
        "Type: expense\n"
        "Amount: 129.90 ILS\n"
        "Date: 2025-09-16\n"
        "Category: subscription\n"
        "Description: Telegram Premium Annual\n"
        "Confidence: 0.87\n\n"
        "Save this transaction?"
    ]
    keyboard = message.answer_kwargs[0]["reply_markup"]
    buttons = keyboard.inline_keyboard[0]
    assert buttons[0].text == "Save transaction"
    assert buttons[0].callback_data == "document_transaction:save"
    assert buttons[1].text == "Cancel"
    assert buttons[1].callback_data == "document_transaction:cancel"
    assert state.state == DocumentTransactionConfirmation.waiting_for_confirmation


def test_handle_parse_document_uses_today_when_ai_date_is_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="129.90")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=None,
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(documents, "date", FixedDate)
    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert "Date: 2026-05-30" in message.answers[0]
    pending = state.data[documents.DOCUMENT_TRANSACTION_STATE_KEY]
    assert pending["transaction"]["date"] == "2026-05-30"


def test_handle_parse_document_successful_ai_parse_saves_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(
            id=4,
            ocr_status="completed",
            ocr_text="Telegram Premium Annual 129.90 ILS",
            transaction_id=None,
        )

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=date(2025, 9, 16),
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    pending = state.data[documents.DOCUMENT_TRANSACTION_STATE_KEY]
    assert pending["document_id"] == 4
    assert pending["transaction"] == {
        "type": "expense",
        "amount": "129.90",
        "currency": "ILS",
        "date": "2025-09-16",
        "category": "subscription",
        "description": "Telegram Premium Annual",
        "confidence": 0.87,
        "needs_confirmation": True,
        "raw_text": "Telegram Premium Annual 129.90 ILS",
    }
    assert state.state == DocumentTransactionConfirmation.waiting_for_confirmation


def test_handle_parse_document_unknown_ai_parse_shows_not_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="unclear text")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
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
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    state = FakeState()
    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        "AI could not confidently detect a transaction from this document.\n\n"
        "Not saved."
    ]
    assert message.answer_kwargs == [{}]
    assert state.state is None
    assert state.data == {}


def test_handle_parse_document_amount_none_shows_not_saved_without_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="receipt")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=None,
            currency="ILS",
            date=None,
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        "AI could not detect transaction amount from this document.\n\n"
        "Not saved."
    ]
    assert message.answer_kwargs == [{}]
    assert state.state is None
    assert state.data == {}


def test_handle_parse_document_low_confidence_shows_not_saved_without_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="receipt")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=None,
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.49,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        "AI confidence is too low to create a transaction from this document.\n\n"
        "Not saved."
    ]
    assert message.answer_kwargs == [{}]
    assert state.state is None
    assert state.data == {}


def test_handle_parse_document_clears_old_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()
    state.data = {
        documents.DOCUMENT_TRANSACTION_STATE_KEY: {
            "document_id": 99,
            "transaction": {"amount": "1.00"},
        },
    }
    state.state = DocumentTransactionConfirmation.waiting_for_confirmation

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="unclear")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
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
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert state.clear_calls == 1
    assert state.state is None
    assert state.data == {}


def test_handle_parse_document_ai_config_error_shows_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="129.90")

    def fail_extract_transaction_from_text(*args: Any, **kwargs: Any) -> Any:
        raise GroqConfigurationError("missing key")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fail_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, FakeState()))  # type: ignore[arg-type]

    assert message.answers == ["AI is not configured. Set GROQ_API_KEY in .env."]


def test_handle_parse_document_linked_document_blocks_ai_parse_and_save_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()
    document = SimpleNamespace(
        id=4,
        ocr_status="completed",
        ocr_text="Telegram Premium Annual 129.90 ILS",
        transaction_id=45,
    )

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return document

    async def fail_create_transaction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("parse_document must not create transactions")

    def fail_extract_transaction_from_text(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("linked document must not call AI extractor")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fail_extract_transaction_from_text,
    )
    monkeypatch.setattr(
        documents,
        "create_transaction",
        fail_create_transaction,
        raising=False,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers == [
        "This document is already linked to transaction 45.\n\n"
        "Unlink it first if you want to create a new transaction:\n"
        "/unlink_document 4"
    ]
    assert message.answer_kwargs == [{}]
    assert state.data == {}
    assert state.state is None
    assert document.transaction_id == 45


def test_handle_parse_document_after_unlink_can_show_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()
    document = SimpleNamespace(
        id=4,
        ocr_status="completed",
        ocr_text="Telegram Premium Annual 129.90 ILS",
        transaction_id=None,
    )

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return document

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=date(2025, 9, 16),
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert message.answers[0].startswith("AI parsed document transaction:")
    assert "reply_markup" in message.answer_kwargs[0]
    assert state.state == DocumentTransactionConfirmation.waiting_for_confirmation


def test_handle_parse_document_sets_fsm_state_and_inline_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = FakeMessage(text="/parse_document 4")
    state = FakeState()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, ocr_status="completed", ocr_text="129.90")

    def fake_extract_transaction_from_text(
        text: str,
        today: date,
    ) -> ExtractedTransaction:
        return ExtractedTransaction(
            type="expense",
            amount=Decimal("129.90"),
            currency="ILS",
            date=date(2025, 9, 16),
            category="subscription",
            description="Telegram Premium Annual",
            confidence=0.87,
            needs_confirmation=True,
            raw_text=text,
        )

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(
        documents,
        "extract_transaction_from_text",
        fake_extract_transaction_from_text,
    )

    asyncio.run(documents.handle_parse_document(message, state))  # type: ignore[arg-type]

    assert documents.handle_parse_document.__annotations__ == {
        "message": documents.Message,
        "state": documents.FSMContext,
        "return": None,
    }
    assert "reply_markup" in message.answer_kwargs[0]
    assert state.state == DocumentTransactionConfirmation.waiting_for_confirmation


def test_document_transaction_callback_data_differs_from_ai_parse() -> None:
    document_keyboard = keyboards.document_transaction_confirmation_keyboard()
    ai_keyboard = keyboards.ai_transaction_confirmation_keyboard()

    document_callback_data = {
        button.callback_data
        for row in document_keyboard.inline_keyboard
        for button in row
    }
    ai_callback_data = {
        button.callback_data
        for row in ai_keyboard.inline_keyboard
        for button in row
    }

    assert document_callback_data == {
        "document_transaction:save",
        "document_transaction:cancel",
    }
    assert document_callback_data.isdisjoint(ai_callback_data)


def test_handle_document_transaction_save_creates_transaction_and_links_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    document = SimpleNamespace(id=4, transaction_id=None)
    created: dict[str, Any] = {}
    linked: dict[str, Any] = {}

    async def fake_get_or_create_user(
        session: object,
        telegram_user_id: int,
        name: str | None = None,
    ) -> SimpleNamespace:
        assert telegram_user_id == 12345
        assert name == "Test User"
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> Any:
        assert user_id == 7
        assert document_id == 4
        return document

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        created.update(kwargs)
        return SimpleNamespace(id=123)

    async def fake_link_document_to_transaction(
        session: object,
        user_id: int,
        document_id: int,
        transaction_id: int,
    ) -> Any:
        linked.update(
            {
                "user_id": user_id,
                "document_id": document_id,
                "transaction_id": transaction_id,
            }
        )
        document.transaction_id = transaction_id
        return document

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fake_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fake_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    transaction_data = created["data"]
    assert created["user_id"] == 7
    assert created["source"] == "document_ocr_ai"
    assert created["status"] == "confirmed"
    assert transaction_data.type == "expense"
    assert transaction_data.amount == Decimal("129.90")
    assert transaction_data.amount_total == Decimal("129.90")
    assert transaction_data.vat_relevant is False
    assert transaction_data.business_use_percent == Decimal("100.00")
    assert transaction_data.balance_impact_type == "business"
    assert transaction_data.currency == "ILS"
    assert transaction_data.date == date(2025, 9, 16)
    assert transaction_data.category == "subscription"
    assert transaction_data.description == "Telegram Premium Annual"
    assert linked == {"user_id": 7, "document_id": 4, "transaction_id": 123}
    assert document.transaction_id == 123
    assert callback.state.data == {}
    assert callback.state.clear_calls == 1
    assert callback.message.edits == [
        {
            "text": "Transaction saved from document.\n\n"
            "Document ID: 4\n"
            "Transaction ID: 123\n"
            "Type: expense\n"
            "Amount: 129.90 ILS\n"
            "Date: 2025-09-16\n"
            "Description: Telegram Premium Annual",
            "reply_markup": None,
        }
    ]


def test_handle_document_transaction_save_falls_back_when_edit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    callback.message.edit_text_error = TelegramBadRequest(None, "message can't be edited")  # type: ignore[arg-type]

    async def fake_get_or_create_user(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, transaction_id=None)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=123)

    async def fake_link_document_to_transaction(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, transaction_id=123)

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fake_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fake_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert callback.message.answers == [
        "Transaction saved from document.\n\n"
        "Document ID: 4\n"
        "Transaction ID: 123\n"
        "Type: expense\n"
        "Amount: 129.90 ILS\n"
        "Date: 2025-09-16\n"
        "Description: Telegram Premium Annual"
    ]


def test_handle_document_transaction_repeated_save_does_not_create_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    created_count = 0

    async def fake_get_or_create_user(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, transaction_id=None)

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        nonlocal created_count
        created_count += 1
        return SimpleNamespace(id=123)

    async def fake_link_document_to_transaction(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(id=4, transaction_id=123)

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fake_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fake_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )
    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert created_count == 1
    assert callback.message.answers == ["No pending document transaction to save."]


def test_handle_document_transaction_save_without_pending_state_returns_message() -> None:
    callback = FakeCallback()

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert callback.message.answers == ["No pending document transaction to save."]
    assert callback.state.clear_calls == 0


def test_handle_document_transaction_save_rejects_foreign_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    created = False

    async def fake_get_or_create_user(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> None:
        assert user_id == 7
        assert document_id == 4
        return None

    async def fail_create_transaction(**kwargs: Any) -> None:
        nonlocal created
        created = True
        raise AssertionError("foreign document transaction must not be created")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fail_create_transaction)

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert created is False
    assert callback.state.data == {}
    assert callback.state.clear_calls == 1
    assert callback.message.answers == ["Document not found."]


def test_handle_document_transaction_save_rejects_document_linked_after_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    document = SimpleNamespace(id=4, transaction_id=45)
    created = False

    async def fake_get_or_create_user(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(
        session: object,
        user_id: int,
        document_id: int,
    ) -> Any:
        assert user_id == 7
        assert document_id == 4
        return document

    async def fail_create_transaction(**kwargs: Any) -> None:
        nonlocal created
        created = True
        raise AssertionError("linked document must not create duplicate transaction")

    async def fail_link_document_to_transaction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("linked document must not be relinked")

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fail_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fail_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert created is False
    assert document.transaction_id == 45
    assert callback.state.data == {}
    assert callback.state.clear_calls == 1
    assert callback.message.edits == [
        {
            "text": "This document is already linked to transaction 45.\n\n"
            "Transaction was not created.",
            "reply_markup": None,
        }
    ]


def test_handle_document_transaction_save_after_unlink_can_create_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    document = SimpleNamespace(id=4, transaction_id=None)

    async def fake_get_or_create_user(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=7)

    async def fake_get_document_by_id(*args: Any, **kwargs: Any) -> Any:
        return document

    async def fake_create_transaction(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(id=123)

    async def fake_link_document_to_transaction(
        session: object,
        user_id: int,
        document_id: int,
        transaction_id: int,
    ) -> Any:
        document.transaction_id = transaction_id
        return document

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_document_by_id", fake_get_document_by_id)
    monkeypatch.setattr(documents, "create_transaction", fake_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fake_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_save(callback, callback.state)  # type: ignore[arg-type]
    )

    assert document.transaction_id == 123
    assert callback.message.edits[0]["text"].startswith(
        "Transaction saved from document."
    )


def test_handle_document_transaction_cancel_does_not_create_or_link_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = FakeCallback(pending_document_transaction())
    document = SimpleNamespace(id=4, transaction_id=45)

    async def fail_create_transaction(**kwargs: Any) -> None:
        raise AssertionError("cancel must not create transaction")

    async def fail_link_document_to_transaction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("cancel must not link document")

    monkeypatch.setattr(documents, "create_transaction", fail_create_transaction)
    monkeypatch.setattr(
        documents,
        "link_document_to_transaction",
        fail_link_document_to_transaction,
    )

    asyncio.run(
        documents.handle_document_transaction_cancel(callback, callback.state)  # type: ignore[arg-type]
    )

    assert document.transaction_id == 45
    assert callback.state.data == {}
    assert callback.state.clear_calls == 1
    assert callback.message.edits == [
        {
            "text": "Document transaction cancelled. Not saved.",
            "reply_markup": None,
        }
    ]


def test_handle_document_transaction_cancel_falls_back_when_edit_fails() -> None:
    callback = FakeCallback(pending_document_transaction())
    callback.message.edit_text_error = TelegramBadRequest(None, "message can't be edited")  # type: ignore[arg-type]

    asyncio.run(
        documents.handle_document_transaction_cancel(callback, callback.state)  # type: ignore[arg-type]
    )

    assert callback.message.answers == ["Document transaction cancelled. Not saved."]


def test_handle_document_transaction_cancel_without_pending_state_returns_message() -> None:
    callback = FakeCallback()

    asyncio.run(
        documents.handle_document_transaction_cancel(callback, callback.state)  # type: ignore[arg-type]
    )

    assert callback.message.answers == ["No pending document transaction to cancel."]
    assert callback.state.clear_calls == 0


def test_handle_document_transaction_repeated_cancel_does_not_fail() -> None:
    callback = FakeCallback(pending_document_transaction())

    asyncio.run(
        documents.handle_document_transaction_cancel(callback, callback.state)  # type: ignore[arg-type]
    )
    asyncio.run(
        documents.handle_document_transaction_cancel(callback, callback.state)  # type: ignore[arg-type]
    )

    assert callback.message.edits == [
        {
            "text": "Document transaction cancelled. Not saved.",
            "reply_markup": None,
        }
    ]
    assert callback.message.answers == ["No pending document transaction to cancel."]


def test_handle_link_document_validates_format() -> None:
    message = FakeMessage(text="/link_document 12")

    asyncio.run(documents.handle_link_document(message))  # type: ignore[arg-type]

    assert message.answers == ["Use format: /link_document 12 45"]


def test_handle_unlink_document_validates_format() -> None:
    message = FakeMessage(text="/unlink_document abc")

    asyncio.run(documents.handle_unlink_document(message))  # type: ignore[arg-type]

    assert message.answers == ["Use format: /unlink_document 12"]


def test_handle_documents_shows_empty_message(monkeypatch: pytest.MonkeyPatch) -> None:
    message = FakeMessage()

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fake_get_last_documents(
        session: object,
        user_id: int,
        limit: int,
    ) -> list[Any]:
        return []

    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "get_last_documents", fake_get_last_documents)

    asyncio.run(documents.handle_documents(message))  # type: ignore[arg-type]

    assert message.answers == ["No documents yet."]


def test_download_error_does_not_create_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    message = FakeMessage(
        photo=[photo()],
        bot=FakeBot(error=RuntimeError("download failed")),
    )

    async def fake_get_or_create_user(**kwargs: Any) -> Any:
        return SimpleNamespace(id=7)

    async def fail_create_document(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Document must not be created when download fails")

    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(document_storage_path=str(tmp_path)),
    )
    monkeypatch.setattr(
        documents,
        "get_async_session_factory",
        lambda: fake_session_factory,
    )
    monkeypatch.setattr(documents, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(documents, "create_document", fail_create_document)

    asyncio.run(documents.handle_photo_document(message))  # type: ignore[arg-type]

    assert message.answers == ["Could not save document. Please try again."]
    assert not list(tmp_path.rglob("*.jpg"))
