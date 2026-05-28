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
        "/income amount description\n"
        "/expense amount description\n"
        "/last"
    )
