from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Available commands:\n"
        "/start\n"
        "/help\n"
        "/profile\n"
        "/balance\n"
        "/recurring\n"
        "/generate_recurring\n"
        "/documents\n"
        "/document document_id\n"
        "/ocr_document document_id\n"
        "/parse_document document_id\n"
        "/link_document document_id transaction_id\n"
        "/unlink_document document_id\n"
        "/income amount description\n"
        "/expense amount description\n"
        "/ai_parse text\n"
        "/last"
    )
