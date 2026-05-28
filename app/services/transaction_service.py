from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate


async def create_transaction(
    session: AsyncSession,
    user_id: int,
    data: TransactionCreate,
) -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        type=data.type,
        amount=data.amount,
        currency=data.currency,
        date=data.date,
        category=data.category,
        description=data.description,
        source="manual",
        status="confirmed",
    )
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction


async def get_last_transactions(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[Transaction]:
    bounded_limit = max(0, min(limit, 20))
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(bounded_limit)
    )
    return list(result.scalars().all())
