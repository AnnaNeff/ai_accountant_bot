from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from app.core.security import is_allowed_user


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_user: User | None = data.get("event_from_user")
        if event_user is None or not is_allowed_user(event_user.id):
            if isinstance(event, Message):
                await event.answer("Access denied.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            return None

        return await handler(event, data)
