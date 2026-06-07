from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.obligation_payment import ObligationPayment
from app.schemas.obligation_payment import ObligationPaymentCreate


async def create_obligation_payment(
    session: AsyncSession,
    user_id: int,
    data: ObligationPaymentCreate,
) -> ObligationPayment:
    payment = ObligationPayment(
        user_id=user_id,
        recurring_rule_id=data.recurring_rule_id,
        transaction_id=data.transaction_id,
        period_start=data.period_start,
        period_end=data.period_end,
        amount=data.amount,
        currency=data.currency,
        status=data.status,
        notes=data.notes,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def get_obligation_payments_for_rule(
    session: AsyncSession,
    user_id: int,
    recurring_rule_id: int,
) -> list[ObligationPayment]:
    result = await session.execute(
        select(ObligationPayment)
        .where(
            ObligationPayment.user_id == user_id,
            ObligationPayment.recurring_rule_id == recurring_rule_id,
        )
        .order_by(
            ObligationPayment.period_start.desc(),
            ObligationPayment.created_at.desc(),
        )
    )
    return list(result.scalars().all())


async def get_recent_obligation_payments(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[ObligationPayment]:
    bounded_limit = max(0, min(limit, 20))
    result = await session.execute(
        select(ObligationPayment)
        .where(ObligationPayment.user_id == user_id)
        .order_by(ObligationPayment.created_at.desc())
        .limit(bounded_limit)
    )
    return list(result.scalars().all())


async def find_existing_paid_obligation_payment(
    session: AsyncSession,
    user_id: int,
    recurring_rule_id: int,
    period_start: date,
    period_end: date,
) -> ObligationPayment | None:
    result = await session.execute(
        select(ObligationPayment).where(
            ObligationPayment.user_id == user_id,
            ObligationPayment.recurring_rule_id == recurring_rule_id,
            ObligationPayment.period_start == period_start,
            ObligationPayment.period_end == period_end,
            ObligationPayment.status == "paid",
        )
    )
    return result.scalar_one_or_none()
