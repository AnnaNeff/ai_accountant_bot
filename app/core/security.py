from app.core.config import get_settings


def is_allowed_user(telegram_user_id: int) -> bool:
    settings = get_settings()
    return telegram_user_id in settings.allowed_telegram_user_ids
