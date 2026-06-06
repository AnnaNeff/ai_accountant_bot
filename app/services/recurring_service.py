import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_rule import RecurringRule
from app.models.transaction import Transaction
from app.schemas.recurring_rule import RecurringRuleCreate


@dataclass(frozen=True)
class RecurringGenerationResult:
    generated_count: int
    skipped_non_auto_pay_count: int


async def create_recurring_rule(
    session: AsyncSession,
    user_id: int,
    data: RecurringRuleCreate,
) -> RecurringRule:
    rule = RecurringRule(
        user_id=user_id,
        type=data.type,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        description=data.description,
        frequency=data.frequency,
        day_of_month=data.day_of_month,
        payment_behavior=data.payment_behavior,
        obligation_type=data.obligation_type,
        affects_balance_when_generated=data.affects_balance_when_generated,
        start_date=data.start_date,
        end_date=data.end_date,
        active=data.active,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def get_active_recurring_rules(
    session: AsyncSession,
    user_id: int,
) -> list[RecurringRule]:
    result = await session.execute(
        select(RecurringRule)
        .where(RecurringRule.user_id == user_id, RecurringRule.active.is_(True))
        .order_by(RecurringRule.day_of_month, RecurringRule.id)
    )
    return list(result.scalars().all())


async def get_all_recurring_rules(
    session: AsyncSession,
    user_id: int,
) -> list[RecurringRule]:
    result = await session.execute(
        select(RecurringRule)
        .where(RecurringRule.user_id == user_id)
        .order_by(RecurringRule.active.desc(), RecurringRule.day_of_month, RecurringRule.id)
    )
    return list(result.scalars().all())


async def get_recurring_rule_by_id(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
) -> RecurringRule | None:
    result = await session.execute(
        select(RecurringRule).where(
            RecurringRule.id == rule_id,
            RecurringRule.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_non_auto_pay_obligations(
    session: AsyncSession,
    user_id: int,
) -> list[RecurringRule]:
    result = await session.execute(
        select(RecurringRule)
        .where(
            RecurringRule.user_id == user_id,
            RecurringRule.active.is_(True),
            RecurringRule.payment_behavior.in_(("manual_pay", "reserve_only")),
        )
        .order_by(RecurringRule.day_of_month, RecurringRule.id)
    )
    return list(result.scalars().all())


async def deactivate_recurring_rule(
    session: AsyncSession,
    user_id: int,
    rule_id: int,
) -> RecurringRule | None:
    result = await session.execute(
        select(RecurringRule).where(
            RecurringRule.id == rule_id,
            RecurringRule.user_id == user_id,
        )
    )
    rule = result.scalar_one_or_none()

    if rule is None:
        return None

    rule.active = False
    await session.commit()
    await session.refresh(rule)
    return rule


def calculate_monthly_due_date(rule: RecurringRule, today: date) -> date | None:
    if rule.frequency != "monthly":
        return None

    last_day = calendar.monthrange(today.year, today.month)[1]
    due_day = min(rule.day_of_month, last_day)
    due_date = date(today.year, today.month, due_day)

    if today < due_date:
        return None
    if rule.start_date > due_date:
        return None
    if rule.end_date is not None and rule.end_date < due_date:
        return None

    return due_date


def should_generate_recurring_transaction(
    rule: RecurringRule,
    today: date,
) -> date | None:
    due_date = calculate_monthly_due_date(rule, today)
    if due_date is None:
        return None
    if rule.last_generated_for_date is not None and rule.last_generated_for_date >= due_date:
        return None

    return due_date


async def generate_recurring_transactions(
    session: AsyncSession,
    user_id: int,
    today: date | None = None,
) -> RecurringGenerationResult:
    generation_date = today or date.today()
    rules = await get_active_recurring_rules(session, user_id)
    created_count = 0
    skipped_non_auto_pay_count = 0

    for rule in rules:
        due_date = should_generate_recurring_transaction(rule, generation_date)
        if due_date is None:
            continue
        if rule.payment_behavior != "auto_pay":
            skipped_non_auto_pay_count += 1
            continue

        transaction = Transaction(
            user_id=user_id,
            type=rule.type,
            amount=rule.amount,
            amount_total=rule.amount,
            vat_relevant=False,
            business_use_percent=Decimal("100.00"),
            balance_impact_type="business",
            currency=rule.currency,
            category=rule.category,
            description=rule.description,
            source="recurring",
            status="confirmed",
            date=due_date,
        )
        session.add(transaction)
        rule.last_generated_for_date = due_date
        created_count += 1

    if created_count:
        await session.commit()

    return RecurringGenerationResult(
        generated_count=created_count,
        skipped_non_auto_pay_count=skipped_non_auto_pay_count,
    )
