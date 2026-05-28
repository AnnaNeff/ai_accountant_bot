from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.session import async_session_factory
from app.models.financial_profile import FinancialProfile
from app.services.financial_profile_service import get_financial_profile
from app.services.user_service import get_or_create_user

router = Router(name="profile")


def format_financial_profile(profile: FinancialProfile | None) -> str:
    if profile is None:
        return "Financial profile is not set. Use bootstrap.yaml to load initial data."

    return (
        "Financial profile:\n\n"
        f"Opening balance: {profile.opening_balance:,.2f}\n"
        f"Currency: {profile.currency}\n"
        f"Opening balance date: {profile.opening_balance_date.isoformat()}"
    )


@router.message(Command("profile"))
async def handle_profile(message: Message) -> None:
    if message.from_user is None:
        return

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session=session,
            telegram_user_id=message.from_user.id,
            name=message.from_user.full_name,
        )
        profile = await get_financial_profile(session, user.id)

    await message.answer(format_financial_profile(profile))
