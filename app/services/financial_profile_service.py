from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_profile import FinancialProfile
from app.schemas.financial_profile import FinancialProfileCreate


async def get_financial_profile(
    session: AsyncSession,
    user_id: int,
) -> FinancialProfile | None:
    result = await session.execute(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_financial_profile(
    session: AsyncSession,
    user_id: int,
    data: FinancialProfileCreate,
) -> FinancialProfile:
    profile = await get_financial_profile(session, user_id)

    if profile is None:
        profile = FinancialProfile(user_id=user_id)
        session.add(profile)

    profile.opening_balance = data.opening_balance
    profile.currency = data.currency
    profile.opening_balance_date = data.opening_balance_date

    await session.commit()
    await session.refresh(profile)
    return profile
