import asyncio

from app.bot.handlers.help import handle_help


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def test_help_includes_vat_report_command() -> None:
    message = FakeMessage()

    asyncio.run(handle_help(message))  # type: ignore[arg-type]

    assert "/vat_report period_start period_end" in message.answers[0]
