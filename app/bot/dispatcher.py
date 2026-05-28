from aiogram import Bot, Dispatcher

from app.bot.handlers.help import router as help_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.transactions import router as transactions_router
from app.bot.middlewares import AccessMiddleware
from app.core.config import Settings


def create_bot_and_dispatcher(settings: Settings) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()

    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.callback_query.middleware(AccessMiddleware())

    dispatcher.include_router(start_router)
    dispatcher.include_router(help_router)
    dispatcher.include_router(transactions_router)

    return bot, dispatcher
