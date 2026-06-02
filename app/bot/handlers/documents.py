from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize

from app.ai.llm_client import GroqConfigurationError
from app.ai.transaction_extractor import extract_transaction_from_text
from app.bot.keyboards import document_transaction_confirmation_keyboard
from app.bot.states import DocumentTransactionConfirmation
from app.core.config import get_settings
from app.models.document import Document
from app.ocr.ocr_service import extract_text_from_image
from app.schemas.ai_extraction import ExtractedTransaction
from app.schemas.document import DocumentCreate
from app.schemas.transaction import TransactionCreate
from app.services.document_service import (
    create_document,
    get_document_by_id,
    get_last_documents,
    link_document_to_transaction,
    save_document_ocr_result,
    unlink_document_from_transaction,
)
from app.services.transaction_service import create_transaction
from app.services.user_service import get_or_create_user
from app.storage.file_storage import build_document_path, calculate_sha256

router = Router(name="documents")

OCR_RESPONSE_TEXT_LIMIT = 3000
OCR_PREVIEW_TEXT_LIMIT = 500
DOCUMENT_TRANSACTION_STATE_KEY = "document_transaction"


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
    amount = f"{transaction.amount:.2f} {transaction.currency}"
    transaction_date = transaction.date or today
    category = transaction.category or "not detected"
    description = transaction.description or "not detected"

    return (
        "AI parsed document transaction:\n\n"
        f"Document ID: {document_id}\n"
        f"Type: {transaction.type}\n"
        f"Amount: {amount}\n"
        f"Date: {transaction_date.isoformat()}\n"
        f"Category: {category}\n"
        f"Description: {description}\n"
        f"Confidence: {transaction.confidence:.2f}\n\n"
        "Save this transaction?"
    )


def transaction_create_from_document_ai_data(data: dict[str, object]) -> TransactionCreate:
    return TransactionCreate(
        type=data["type"],  # type: ignore[arg-type]
        amount=Decimal(str(data["amount"])),
        currency=str(data.get("currency") or "ILS"),
        date=date.fromisoformat(str(data["date"])),
        category=data.get("category"),  # type: ignore[arg-type]
        description=data.get("description"),  # type: ignore[arg-type]
    )


def format_document_transaction_saved_message(
    document_id: int,
    transaction_id: int,
    transaction_data: TransactionCreate,
) -> str:
    return (
        "Transaction saved from document.\n\n"
        f"Document ID: {document_id}\n"
        f"Transaction ID: {transaction_id}\n"
        f"Type: {transaction_data.type}\n"
        f"Amount: {transaction_data.amount:.2f} {transaction_data.currency}\n"
        f"Date: {transaction_data.date.isoformat()}\n"
        f"Description: {transaction_data.description or 'not detected'}"
    )


async def replace_callback_message_text(
    callback: CallbackQuery,
    text: str,
) -> None:
    if callback.message is None:
        return

    try:
        await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        await callback.message.answer(text)


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
async def handle_parse_document(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()

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

    if transaction.amount is None:
        await message.answer(
            "AI could not detect transaction amount from this document.\n\n"
            "Not saved."
        )
        return

    if transaction.confidence < 0.5:
        await message.answer(
            "AI confidence is too low to create a transaction from this document.\n\n"
            "Not saved."
        )
        return

    transaction_to_confirm = transaction.model_copy(
        update={"date": transaction.date or today},
    )
    await state.update_data(
        {
            DOCUMENT_TRANSACTION_STATE_KEY: {
                "document_id": document_id,
                "transaction": transaction_to_confirm.model_dump(mode="json"),
            },
        },
    )
    await state.set_state(DocumentTransactionConfirmation.waiting_for_confirmation)
    await message.answer(
        format_document_ai_preview(document_id, transaction_to_confirm, today),
        reply_markup=document_transaction_confirmation_keyboard(),
    )


@router.callback_query(F.data == "document_transaction:save")
async def handle_document_transaction_save(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    state_data = await state.get_data()
    pending = state_data.get(DOCUMENT_TRANSACTION_STATE_KEY)

    if not isinstance(pending, dict):
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("No pending document transaction to save.")
        return

    if callback.from_user is None:
        return

    document_id = pending.get("document_id")
    transaction_payload = pending.get("transaction")
    if not isinstance(document_id, int) or not isinstance(transaction_payload, dict):
        await state.clear()
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("No pending document transaction to save.")
        return

    transaction_data = transaction_create_from_document_ai_data(transaction_payload)
    session_factory = get_async_session_factory()

    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=callback.from_user.id,
            name=callback.from_user.full_name,
        )
        document = await get_document_by_id(session, user.id, document_id)
        if document is None:
            await state.clear()
            await callback.answer()
            if callback.message is not None:
                await callback.message.answer("Document not found.")
            return

        transaction = await create_transaction(
            session=session,
            user_id=user.id,
            data=transaction_data,
            source="document_ocr_ai",
            status="confirmed",
        )
        await link_document_to_transaction(
            session,
            user.id,
            document_id,
            transaction.id,
        )

    await state.clear()
    await callback.answer()
    await replace_callback_message_text(
        callback,
        format_document_transaction_saved_message(
            document_id=document_id,
            transaction_id=transaction.id,
            transaction_data=transaction_data,
        ),
    )


@router.callback_query(F.data == "document_transaction:cancel")
async def handle_document_transaction_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    state_data = await state.get_data()
    pending = state_data.get(DOCUMENT_TRANSACTION_STATE_KEY)

    if not isinstance(pending, dict):
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("No pending document transaction to cancel.")
        return

    await state.clear()
    await callback.answer()
    await replace_callback_message_text(
        callback,
        "Document transaction cancelled. Not saved.",
    )


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
