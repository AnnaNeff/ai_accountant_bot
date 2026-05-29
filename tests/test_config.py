from app.core.config import Settings


def test_settings_parses_allowed_user_ids() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        ALLOWED_TELEGRAM_USER_IDS="123, 456,789",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        GROQ_API_KEY="test-ai-key",
        LOG_LEVEL="DEBUG",
    )

    assert settings.allowed_telegram_user_ids == [123, 456, 789]
    assert settings.groq_api_key == "test-ai-key"
    assert settings.groq_model == "llama-3.1-8b-instant"
    assert settings.log_level == "DEBUG"


def test_settings_accepts_groq_model_override() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="test-token",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/app",
        GROQ_API_KEY="",
        GROQ_MODEL="groq-test-model",
    )

    assert settings.groq_api_key is None
    assert settings.groq_model == "groq-test-model"
