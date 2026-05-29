from datetime import date

from app.ai.extraction_prompts import TRANSACTION_EXTRACTION_SYSTEM_PROMPT
from app.core.config import Settings, get_settings


class GroqConfigurationError(RuntimeError):
    """Raised when AI extraction is requested without Groq configuration."""


def extract_transaction_json(
    text: str,
    today: date,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    if not settings.groq_api_key:
        raise GroqConfigurationError("GROQ_API_KEY is not configured.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise GroqConfigurationError("The openai package is not installed.") from exc

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": TRANSACTION_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Today is {today.isoformat()}.\n"
                    f"Extract a possible transaction from this user text:\n{text}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    return response.choices[0].message.content or ""
