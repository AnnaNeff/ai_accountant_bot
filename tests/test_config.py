from app.core.config import Settings


def test_settings_parses_allowed_user_ids() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        ALLOWED_TELEGRAM_USER_IDS="123, 456,789",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        LOG_LEVEL="DEBUG",
    )

    assert settings.allowed_telegram_user_ids == [123, 456, 789]
    assert settings.log_level == "DEBUG"
