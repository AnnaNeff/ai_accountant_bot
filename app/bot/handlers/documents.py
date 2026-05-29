from datetime import datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, PhotoSize

from app.core.config import get_settings
from app.models.document import Document
from app.schemas.document import DocumentCreate
from app.services.document_service import create_document, get_last_documents
from app.services.user_service import get_or_create_user
from app.storage.file_storage import build_document_path, calculate_sha256

router = Router(name="documents")


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def select_largest_photo(photos: list[PhotoSize]) -> PhotoSize:
    return max(
        photos,
        key=lambda photo: photo.file_size or photo.width * photo.height,
    )


def format_documents_list(documents: list[Document]) -> str:
    if not documents:
        return "No documents yet."

    rows = ["Documents:", ""]
    for number, document in enumerate(documents, start=1):
        created_at = document.created_at
        created_date = (
            created_at.date().isoformat()
            if isinstance(created_at, datetime)
            else str(created_at)
        )
        rows.append(
            f"{number}. ID {document.id} | {document.status} | {created_date}"
        )
    return "\n".join(rows)


async def download_photo(file_id: str, destination: Path, message: Message) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    await message.bot.download(file=file_id, destination=destination)


@router.message(Command("documents"))
async def handle_documents(message: Message) -> None:
    if message.from_user is None:
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        documents = await get_last_documents(session, user.id, limit=10)

    await message.answer(format_documents_list(documents))


@router.message(F.photo)
async def handle_photo_document(message: Message) -> None:
    if message.from_user is None or not message.photo:
        return

    settings = get_settings()
    photo = select_largest_photo(list(message.photo))
    session_factory = get_async_session_factory()

    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )

    document_path = build_document_path(settings.document_storage_path, user.id)

    try:
        await download_photo(photo.file_id, document_path, message)
        file_hash = calculate_sha256(document_path)
    except Exception:
        if document_path.exists():
            document_path.unlink()
        await message.answer("Could not save document. Please try again.")
        return

    document_data = DocumentCreate(
        transaction_id=None,
        telegram_file_id=photo.file_id,
        local_path=str(document_path),
        file_hash=file_hash,
        mime_type="image/jpeg",
        file_size_bytes=photo.file_size,
        status="uploaded",
    )

    async with session_factory() as session:
        document = await create_document(session, user.id, document_data)

    await message.answer(
        "Document saved.\n\n"
        f"ID: {document.id}\n"
        f"Status: {document.status}\n\n"
        "OCR is not implemented yet."
    )
