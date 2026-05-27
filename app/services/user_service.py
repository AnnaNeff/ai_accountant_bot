from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    name: str | None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        return user

    user = User(telegram_user_id=telegram_user_id, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
