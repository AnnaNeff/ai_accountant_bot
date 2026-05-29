import pytest
from pydantic import ValidationError

from app.schemas.document import DocumentCreate


def test_document_create_validates_uploaded_status() -> None:
    document = DocumentCreate(
        telegram_file_id="telegram-file-id",
        local_path="data/private/documents/1/2026/05/file.jpg",
        file_hash="a" * 64,
        mime_type="image/jpeg",
        file_size_bytes=12345,
    )

    assert document.transaction_id is None
    assert document.status == "uploaded"


def test_document_create_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(
            telegram_file_id="telegram-file-id",
            local_path="data/private/documents/1/2026/05/file.jpg",
            file_hash="a" * 64,
            status="processed",
        )
