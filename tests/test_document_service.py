import asyncio
from datetime import date
from decimal import Decimal
from typing import Any

from app.models.document import Document
from app.models.transaction import Transaction
from app.services.document_service import (
    get_document_by_id,
    link_document_to_transaction,
    save_document_ocr_result,
    unlink_document_from_transaction,
)


class FakeScalarResult:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def all(self) -> list[Any]:
        return self.items

    def first(self) -> Any | None:
        return self.items[0] if self.items else None


class FakeResult:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.items)


class FakeSession:
    def __init__(
        self,
        documents: list[Document] | None = None,
        transactions: list[Transaction] | None = None,
    ) -> None:
        self.documents = documents or []
        self.transactions = transactions or []
        self.committed = False
        self.refreshed: Any | None = None

    async def execute(self, statement: Any) -> FakeResult:
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        entity = statement.column_descriptions[0]["entity"]

        if entity is Document:
            return FakeResult(
                [
                    document
                    for document in self.documents
                    if f"documents.id = {document.id}" in sql
                    and f"documents.user_id = {document.user_id}" in sql
                ]
            )

        if entity is Transaction:
            return FakeResult(
                [
                    transaction
                    for transaction in self.transactions
                    if f"transactions.id = {transaction.id}" in sql
                    and f"transactions.user_id = {transaction.user_id}" in sql
                ]
            )

        return FakeResult([])

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, item: Any) -> None:
        self.refreshed = item


def make_document(**overrides: Any) -> Document:
    data = {
        "id": 12,
        "user_id": 7,
        "transaction_id": None,
        "telegram_file_id": "telegram-file-id",
        "local_path": "data/private/documents/7/file.jpg",
        "file_hash": "a" * 64,
        "mime_type": "image/jpeg",
        "file_size_bytes": 123,
        "status": "uploaded",
    }
    data.update(overrides)
    return Document(**data)


def make_transaction(**overrides: Any) -> Transaction:
    data = {
        "id": 45,
        "user_id": 7,
        "type": "expense",
        "amount": Decimal("10.00"),
        "date": date(2026, 5, 30),
    }
    data.update(overrides)
    return Transaction(**data)


def test_get_document_by_id_returns_only_current_user_document() -> None:
    own_document = make_document(id=12, user_id=7)
    other_document = make_document(id=12, user_id=8)
    session = FakeSession(documents=[own_document, other_document])

    result = asyncio.run(get_document_by_id(session, 7, 12))  # type: ignore[arg-type]

    assert result is own_document


def test_link_document_to_transaction_links_same_user_transaction() -> None:
    document = make_document(id=12, user_id=7)
    transaction = make_transaction(id=45, user_id=7)
    session = FakeSession(documents=[document], transactions=[transaction])

    result = asyncio.run(
        link_document_to_transaction(session, 7, 12, 45)  # type: ignore[arg-type]
    )

    assert result is document
    assert document.transaction_id == 45
    assert session.committed is True
    assert session.refreshed is document


def test_link_document_to_transaction_does_not_link_other_user_transaction() -> None:
    document = make_document(id=12, user_id=7)
    transaction = make_transaction(id=45, user_id=8)
    session = FakeSession(documents=[document], transactions=[transaction])

    result = asyncio.run(
        link_document_to_transaction(session, 7, 12, 45)  # type: ignore[arg-type]
    )

    assert result is None
    assert document.transaction_id is None
    assert session.committed is False


def test_unlink_document_from_transaction_clears_transaction_id() -> None:
    document = make_document(id=12, user_id=7, transaction_id=45)
    session = FakeSession(documents=[document])

    result = asyncio.run(
        unlink_document_from_transaction(session, 7, 12)  # type: ignore[arg-type]
    )

    assert result is document
    assert document.transaction_id is None
    assert session.committed is True
    assert session.refreshed is document


def test_save_document_ocr_result_saves_completed() -> None:
    document = make_document(id=12, user_id=7)
    session = FakeSession(documents=[document])

    result = asyncio.run(
        save_document_ocr_result(
            session,
            user_id=7,
            document_id=12,
            ocr_text="Milk\nBread",
            success=True,
        )  # type: ignore[arg-type]
    )

    assert result is document
    assert document.ocr_text == "Milk\nBread"
    assert document.ocr_status == "completed"
    assert document.ocr_error is None
    assert document.ocr_processed_at is not None
    assert session.committed is True
    assert session.refreshed is document


def test_save_document_ocr_result_saves_failed() -> None:
    document = make_document(id=12, user_id=7, ocr_text="old text")
    session = FakeSession(documents=[document])

    result = asyncio.run(
        save_document_ocr_result(
            session,
            user_id=7,
            document_id=12,
            ocr_text="",
            success=False,
            error_message="tesseract failed",
        )  # type: ignore[arg-type]
    )

    assert result is document
    assert document.ocr_text == "old text"
    assert document.ocr_status == "failed"
    assert document.ocr_error == "tesseract failed"
    assert document.ocr_processed_at is not None
    assert session.committed is True
    assert session.refreshed is document


def test_save_document_ocr_result_does_not_update_other_user_document() -> None:
    document = make_document(id=12, user_id=8)
    session = FakeSession(documents=[document])

    result = asyncio.run(
        save_document_ocr_result(
            session,
            user_id=7,
            document_id=12,
            ocr_text="Milk",
            success=True,
        )  # type: ignore[arg-type]
    )

    assert result is None
    assert document.ocr_text is None
    assert session.committed is False
