import logging
from datetime import date
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.ai.llm_client import GroqConfigurationError
from app.ai.transaction_extractor import extract_transaction_from_text
from app.bot.keyboards import ai_transaction_confirmation_keyboard
from app.bot.states import AiTransactionConfirmation
from app.schemas.ai_extraction import ExtractedTransaction
from app.schemas.transaction import TransactionCreate
from app.services.transaction_service import create_transaction
from app.services.user_service import get_or_create_user

router = Router(name="ai_parse")
logger = logging.getLogger(__name__)

AI_PARSE_USAGE = "Use format: /ai_parse received 1500 ILS for consulting"
AI_TRANSACTION_STATE_KEY = "ai_transaction"


def get_async_session_factory():
    from app.db.session import async_session_factory

    return async_session_factory


def parse_ai_parse_command(text: str | None) -> str | None:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None
    return parts[1].strip()


def format_extracted_transaction_preview(transaction: ExtractedTransaction) -> str:
    amount = f"{transaction.amount:.2f} {transaction.currency}"
    transaction_date = (
        transaction.date.isoformat() if transaction.date else date.today().isoformat()
    )
    category = transaction.category or "not detected"
    description = transaction.description or "not detected"

    return (
        "AI parsed transaction:\n\n"
        f"Type: {transaction.type}\n"
        f"Amount: {amount}\n"
        f"Date: {transaction_date}\n"
        f"Category: {category}\n"
        f"Description: {description}\n"
        "\n"
        "Save this transaction?"
    )


@router.message(Command("ai_parse"))
async def handle_ai_parse(message: Message, state: FSMContext) -> None:
    user_text = parse_ai_parse_command(message.text)
    if user_text is None:
        await message.answer(AI_PARSE_USAGE)
        return

    await state.clear()

    today = date.today()
    try:
        transaction = extract_transaction_from_text(user_text, today)
    except GroqConfigurationError:
        await message.answer("AI is not configured. Set GROQ_API_KEY in .env.")
        return

    if transaction.type == "unknown" or transaction.amount is None:
        await message.answer("AI could not confidently detect a transaction.\n\nNot saved.")
        return

    if transaction.confidence < 0.5:
        await message.answer("AI confidence is too low to create a transaction.\n\nNot saved.")
        return

    transaction_to_confirm = transaction.model_copy(
        update={"date": transaction.date or today},
    )
    logger.info(
        "AI transaction parsed for confirmation: type=%s amount=%s currency=%s "
        "date=%s category=%s confidence=%.2f",
        transaction_to_confirm.type,
        transaction_to_confirm.amount,
        transaction_to_confirm.currency,
        transaction_to_confirm.date,
        transaction_to_confirm.category,
        transaction_to_confirm.confidence,
    )

    await state.update_data(
        {AI_TRANSACTION_STATE_KEY: transaction_to_confirm.model_dump(mode="json")},
    )
    await state.set_state(AiTransactionConfirmation.waiting_for_confirmation)
    await message.answer(
        format_extracted_transaction_preview(transaction_to_confirm),
        reply_markup=ai_transaction_confirmation_keyboard(),
    )


def transaction_create_from_ai_data(data: dict[str, object]) -> TransactionCreate:
    return TransactionCreate(
        type=data["type"],  # type: ignore[arg-type]
        amount=Decimal(str(data["amount"])),
        currency=str(data.get("currency") or "ILS"),
        date=date.fromisoformat(str(data["date"])),
        category=data.get("category"),  # type: ignore[arg-type]
        description=data.get("description"),  # type: ignore[arg-type]
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


@router.callback_query(F.data == "ai_transaction:save")
async def handle_ai_transaction_save(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    state_data = await state.get_data()
    pending = state_data.get(AI_TRANSACTION_STATE_KEY)

    if not isinstance(pending, dict):
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("No pending AI transaction to save.")
        return

    if callback.from_user is None:
        return

    transaction_data = transaction_create_from_ai_data(pending)
    session_factory = get_async_session_factory()

    async with session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=callback.from_user.id,
            name=callback.from_user.full_name,
        )
        await create_transaction(
            session=session,
            user_id=user.id,
            data=transaction_data,
            source="ai_text",
            status="confirmed",
        )

    await state.clear()
    await callback.answer()
    await replace_callback_message_text(callback, "Transaction saved.")


@router.callback_query(F.data == "ai_transaction:cancel")
async def handle_ai_transaction_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    state_data = await state.get_data()
    pending = state_data.get(AI_TRANSACTION_STATE_KEY)

    if not isinstance(pending, dict):
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("No pending AI transaction to cancel.")
        return

    await state.clear()
    await callback.answer()
    await replace_callback_message_text(callback, "AI transaction cancelled. Not saved.")
