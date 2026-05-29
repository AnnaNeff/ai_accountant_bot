from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.ai.llm_client import GroqConfigurationError
from app.ai.transaction_extractor import extract_transaction_from_text
from app.schemas.ai_extraction import ExtractedTransaction

router = Router(name="ai_parse")

AI_PARSE_USAGE = "Use format: /ai_parse received 1500 ILS for consulting"


def parse_ai_parse_command(text: str | None) -> str | None:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None
    return parts[1].strip()


def format_extracted_transaction(transaction: ExtractedTransaction) -> str:
    if transaction.type == "unknown":
        return "AI could not confidently detect a transaction.\n\nNot saved."

    amount = (
        f"{transaction.amount:.2f} {transaction.currency}"
        if transaction.amount is not None
        else f"not detected {transaction.currency}"
    )
    transaction_date = transaction.date.isoformat() if transaction.date else "not detected"
    category = transaction.category or "not detected"
    description = transaction.description or "not detected"
    needs_confirmation = "yes" if transaction.needs_confirmation else "no"

    return (
        "AI parsed transaction:\n\n"
        f"Type: {transaction.type}\n"
        f"Amount: {amount}\n"
        f"Date: {transaction_date}\n"
        f"Category: {category}\n"
        f"Description: {description}\n"
        f"Confidence: {transaction.confidence:.2f}\n"
        f"Needs confirmation: {needs_confirmation}\n\n"
        "Not saved. This is preview only."
    )


@router.message(Command("ai_parse"))
async def handle_ai_parse(message: Message) -> None:
    user_text = parse_ai_parse_command(message.text)
    if user_text is None:
        await message.answer(AI_PARSE_USAGE)
        return

    try:
        transaction = extract_transaction_from_text(user_text, date.today())
    except GroqConfigurationError:
        await message.answer("AI is not configured. Set GROQ_API_KEY in .env.")
        return

    await message.answer(format_extracted_transaction(transaction))
