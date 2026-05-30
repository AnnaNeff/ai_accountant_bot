import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.bot.handlers import documents
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

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


class FakeSessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def fake_session_factory() -> FakeSessionContext:
    return FakeSessionContext()


def photo(file_id: str = "telegram-file-id", file_size: int | None = 14) -> Any:
    return SimpleNamespace(
        file_id=file_id,
        file_size=file_size,
        width=1280,
        height=960,
    )


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
        "OCR is not implemented yet."
    ]


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
                transaction_id=45,
                created_at=datetime(2026, 5, 30),
            ),
            SimpleNamespace(
                id=11,
                status="uploaded",
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
        "1. ID 12 | uploaded | transaction 45 | 2026-05-30\n"
        "2. ID 11 | uploaded | not linked | 2026-05-29"
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
        "Created at: 2026-05-30\n"
        "Transaction ID: not linked\n"
        "File size: 123456 bytes"
    ]


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
