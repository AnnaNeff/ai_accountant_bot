import asyncio

from app.bot.dispatcher import create_bot_and_dispatcher
from app.core.config import get_settings
from app.core.logging import setup_logging


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    bot, dispatcher = create_bot_and_dispatcher(settings)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
