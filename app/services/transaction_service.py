from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate


async def create_transaction(
    session: AsyncSession,
    user_id: int,
    data: TransactionCreate,
    source: str = "manual",
    status: str = "confirmed",
    commit: bool = True,
) -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        type=data.type,
        amount=data.amount,
        amount_total=data.amount_total,
        amount_net=data.amount_net,
        vat_amount=data.vat_amount,
        vat_rate=data.vat_rate,
        vat_included=data.vat_included,
        vat_relevant=data.vat_relevant,
        business_use_percent=data.business_use_percent,
        tax_deductible=data.tax_deductible,
        tax_category=data.tax_category,
        balance_impact_type=data.balance_impact_type,
        currency=data.currency,
        date=data.date,
        category=data.category,
        description=data.description,
        source=source,
        status=status,
    )
    session.add(transaction)
    if commit:
        await session.commit()
        await session.refresh(transaction)
    else:
        await session.flush()
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


async def has_similar_obligation_payment_today(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    category: str | None,
    descriptions: tuple[str, ...],
    payment_date: date,
) -> bool:
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.source == "obligation_manual_payment",
            Transaction.date == payment_date,
            Transaction.category == category,
            Transaction.amount == amount,
        )
    )
    normalized_descriptions = {
        description.strip().casefold()
        for description in descriptions
        if description.strip()
    }

    for transaction in result.scalars().all():
        existing_description = (transaction.description or "").strip().casefold()
        if existing_description and any(
            description in existing_description
            or existing_description in description
            for description in normalized_descriptions
        ):
            return True

    return False
