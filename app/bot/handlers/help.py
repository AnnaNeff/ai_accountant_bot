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
        "/obligations\n"
        "/obligation_status\n"
        "/obligation_payments\n"
        "/pay_obligation rule_id amount period_start period_end description\n"
        "/generate_recurring\n"
        "/documents\n"
        "/document document_id\n"
        "/ocr_document document_id\n"
        "/parse_document document_id\n"
        "/link_document document_id transaction_id\n"
        "/unlink_document document_id\n"
        "/income amount description\n"
        "/expense amount description\n"
        "/transaction transaction_id\n"
        "/set_transaction_tax transaction_id field value\n"
        "/vat_report period_start period_end\n"
        "/ai_parse text\n"
        "/last"
    )
