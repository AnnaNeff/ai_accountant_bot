from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_user_ids: list[int] = Field(
        default_factory=list,
        alias="ALLOWED_TELEGRAM_USER_IDS",
    )
    database_url: str = Field(alias="DATABASE_URL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    document_storage_path: str = Field(
        default="data/private/documents",
        alias="DOCUMENT_STORAGE_PATH",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_telegram_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, value: object) -> list[int] | object:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def normalize_groq_api_key(cls, value: object) -> str | None | object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
