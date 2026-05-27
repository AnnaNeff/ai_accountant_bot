from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.session import async_session_factory
from app.services.user_service import get_or_create_user

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )

    await message.answer("AI Accountant Bot is running. Access confirmed.")
