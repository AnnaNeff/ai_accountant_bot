from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.ai_parse import router as ai_parse_router
from app.bot.handlers.balance import router as balance_router
from app.bot.handlers.documents import router as documents_router
from app.bot.handlers.help import router as help_router
from app.bot.handlers.income_tax import router as income_tax_router
from app.bot.handlers.profile import router as profile_router
from app.bot.handlers.recurring import router as recurring_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.transactions import router as transactions_router
from app.bot.handlers.vat import router as vat_router
from app.bot.middlewares import AccessMiddleware
from app.core.config import Settings


def create_bot_and_dispatcher(settings: Settings) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())

    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.callback_query.middleware(AccessMiddleware())

    dispatcher.include_router(start_router)
    dispatcher.include_router(help_router)
    dispatcher.include_router(income_tax_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(balance_router)
    dispatcher.include_router(recurring_router)
    dispatcher.include_router(transactions_router)
    dispatcher.include_router(vat_router)
    dispatcher.include_router(documents_router)
    dispatcher.include_router(ai_parse_router)

    return bot, dispatcher
