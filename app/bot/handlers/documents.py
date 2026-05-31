from datetime import date, datetime
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, PhotoSize

from app.ai.llm_client import GroqConfigurationError
from app.ai.transaction_extractor import extract_transaction_from_text
from app.core.config import get_settings
from app.models.document import Document
from app.ocr.ocr_service import extract_text_from_image
from app.schemas.ai_extraction import ExtractedTransaction
from app.schemas.document import DocumentCreate
from app.services.document_service import (
    create_document,
    get_document_by_id,
    get_last_documents,
    link_document_to_transaction,
    save_document_ocr_result,
    unlink_document_from_transaction,
)
from app.services.user_service import get_or_create_user
from app.storage.file_storage import build_document_path, calculate_sha256

router = Router(name="documents")

OCR_RESPONSE_TEXT_LIMIT = 3000
OCR_PREVIEW_TEXT_LIMIT = 500


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
        transaction_label = (
            f"transaction {document.transaction_id}"
            if document.transaction_id is not None
            else "not linked"
        )
        ocr_status = getattr(document, "ocr_status", "not_started")
        rows.append(
            f"{number}. ID {document.id} | {document.status} | OCR {ocr_status} | "
            f"{transaction_label} | {created_date}"
        )
    return "\n".join(rows)


def format_document_details(document: Document) -> str:
    created_at = document.created_at
    created_date = (
        created_at.date().isoformat()
        if isinstance(created_at, datetime)
        else str(created_at)
    )
    transaction_label = (
        str(document.transaction_id)
        if document.transaction_id is not None
        else "not linked"
    )
    file_size = (
        f"{document.file_size_bytes} bytes"
        if document.file_size_bytes is not None
        else "unknown"
    )
    ocr_status = getattr(document, "ocr_status", "not_started")
    ocr_processed_at = getattr(document, "ocr_processed_at", None)
    ocr_processed_label = (
        ocr_processed_at.isoformat()
        if isinstance(ocr_processed_at, datetime)
        else "not processed"
    )
    rows = [
        "Document details:\n\n"
        f"ID: {document.id}\n"
        f"Status: {document.status}\n"
        f"OCR status: {ocr_status}\n"
        f"OCR processed at: {ocr_processed_label}\n"
        f"Created at: {created_date}\n"
        f"Transaction ID: {transaction_label}\n"
        f"File size: {file_size}"
    ]
    ocr_text = getattr(document, "ocr_text", None)
    if ocr_text:
        preview = ocr_text[:OCR_PREVIEW_TEXT_LIMIT]
        if len(ocr_text) > OCR_PREVIEW_TEXT_LIMIT:
            preview = f"{preview}\n... text truncated"
        rows.append(f"\n\nOCR text preview:\n{preview}")
    return "".join(rows)


def format_ocr_success_message(document_id: int, ocr_text: str) -> str:
    if not ocr_text:
        return (
            "OCR completed, but no text was recognized.\n\n"
            f"Document ID: {document_id}"
        )

    display_text = ocr_text[:OCR_RESPONSE_TEXT_LIMIT]
    if len(ocr_text) > OCR_RESPONSE_TEXT_LIMIT:
        display_text = f"{display_text}\n... text truncated"

    return (
        "OCR completed.\n\n"
        f"Document ID: {document_id}\n\n"
        "Recognized text:\n"
        f"{display_text}"
    )


def format_document_ai_preview(
    document_id: int,
    transaction: ExtractedTransaction,
    today: date,
) -> str:
    amount = (
        f"{transaction.amount:.2f} {transaction.currency}"
        if transaction.amount is not None
        else f"not detected {transaction.currency}"
    )
    transaction_date = transaction.date or today
    category = transaction.category or "not detected"
    description = transaction.description or "not detected"
    needs_confirmation = "yes" if transaction.needs_confirmation else "no"

    return (
        "AI parsed document transaction:\n\n"
        f"Document ID: {document_id}\n"
        f"Type: {transaction.type}\n"
        f"Amount: {amount}\n"
        f"Date: {transaction_date.isoformat()}\n"
        f"Category: {category}\n"
        f"Description: {description}\n"
        f"Confidence: {transaction.confidence:.2f}\n"
        f"Needs confirmation: {needs_confirmation}\n\n"
        "Not saved. This is preview only."
    )


def parse_single_int_command(text: str | None) -> int | None:
    parts = (text or "").split()
    if len(parts) != 2:
        return None

    try:
        return int(parts[1])
    except ValueError:
        return None


def parse_two_int_command(text: str | None) -> tuple[int, int] | None:
    parts = (text or "").split()
    if len(parts) != 3:
        return None

    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


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


@router.message(Command("document"))
async def handle_document(message: Message) -> None:
    if message.from_user is None:
        return

    document_id = parse_single_int_command(message.text)
    if document_id is None:
        await message.answer("Use format: /document 12")
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        document = await get_document_by_id(session, user.id, document_id)

    if document is None:
        await message.answer("Document not found.")
        return

    await message.answer(format_document_details(document))


@router.message(Command("link_document"))
async def handle_link_document(message: Message) -> None:
    if message.from_user is None:
        return

    parsed = parse_two_int_command(message.text)
    if parsed is None:
        await message.answer("Use format: /link_document 12 45")
        return

    document_id, transaction_id = parsed
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        document = await link_document_to_transaction(
            session,
            user.id,
            document_id,
            transaction_id,
        )

    if document is None:
        await message.answer("Document or transaction not found.")
        return

    await message.answer(
        "Document linked to transaction.\n\n"
        f"Document ID: {document.id}\n"
        f"Transaction ID: {document.transaction_id}"
    )


@router.message(Command("unlink_document"))
async def handle_unlink_document(message: Message) -> None:
    if message.from_user is None:
        return

    document_id = parse_single_int_command(message.text)
    if document_id is None:
        await message.answer("Use format: /unlink_document 12")
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        document = await unlink_document_from_transaction(session, user.id, document_id)

    if document is None:
        await message.answer("Document not found.")
        return

    await message.answer(
        "Document unlinked from transaction.\n\n"
        f"Document ID: {document.id}"
    )


@router.message(Command("ocr_document"))
async def handle_ocr_document(message: Message) -> None:
    if message.from_user is None:
        return

    document_id = parse_single_int_command(message.text)
    if document_id is None:
        await message.answer("Use format: /ocr_document 12")
        return

    settings = get_settings()
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        document = await get_document_by_id(session, user.id, document_id)
        if document is None:
            await message.answer("Document not found.")
            return

        image_path = Path(document.local_path)
        if not image_path.exists():
            await save_document_ocr_result(
                session=session,
                user_id=user.id,
                document_id=document_id,
                ocr_text="",
                success=False,
                error_message=f"Document file not found: {image_path}",
            )
            await message.answer("Document file not found.")
            return

        try:
            ocr_text = extract_text_from_image(image_path, settings.ocr_languages)
        except Exception as error:
            await save_document_ocr_result(
                session=session,
                user_id=user.id,
                document_id=document_id,
                ocr_text="",
                success=False,
                error_message=str(error),
            )
            await message.answer(
                "OCR failed. Please check the document image and OCR setup."
            )
            return

        await save_document_ocr_result(
            session=session,
            user_id=user.id,
            document_id=document_id,
            ocr_text=ocr_text,
            success=True,
        )

    await message.answer(format_ocr_success_message(document_id, ocr_text))


@router.message(Command("parse_document"))
async def handle_parse_document(message: Message) -> None:
    if message.from_user is None:
        return

    document_id = parse_single_int_command(message.text)
    if document_id is None:
        await message.answer("Use format: /parse_document 12")
        return

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        document = await get_document_by_id(session, user.id, document_id)

    if document is None:
        await message.answer("Document not found.")
        return

    ocr_text = getattr(document, "ocr_text", None)
    if getattr(document, "ocr_status", None) != "completed" or not ocr_text:
        await message.answer(
            "Document has no completed OCR text. Run /ocr_document first."
        )
        return

    today = date.today()
    try:
        transaction = extract_transaction_from_text(ocr_text, today)
    except GroqConfigurationError:
        await message.answer("AI is not configured. Set GROQ_API_KEY in .env.")
        return

    if transaction.type == "unknown":
        await message.answer(
            "AI could not confidently detect a transaction from this document.\n\n"
            "Not saved."
        )
        return

    await message.answer(format_document_ai_preview(document_id, transaction, today))


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
        "OCR is available. Use /ocr_document <document_id> to extract text."
    )
