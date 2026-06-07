import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.obligation_payment import ObligationPayment
from app.models.recurring_rule import RecurringRule

ObligationStatus = Literal["paid", "unpaid", "overdue"]


@dataclass(frozen=True)
class ExpectedObligationPeriod:
    rule_id: int
    description: str
    obligation_type: str
    payment_behavior: str
    period_start: date
    period_end: date
    due_date: date
    status: ObligationStatus
    amount: Decimal
    currency: str
    transaction_id: int | None


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def _month_start(index: int) -> date:
    year, month_zero_based = divmod(index, 12)
    return date(year, month_zero_based + 1, 1)


def _month_end(index: int) -> date:
    month_start = _month_start(index)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return date(month_start.year, month_start.month, last_day)


def _due_date(
    period_end: date,
    due_day: int | None,
    fallback_day: int,
    month_offset: int,
) -> date:
    due_month_index = _month_index(period_end) + month_offset
    due_month = _month_start(due_month_index)
    requested_day = due_day if due_day is not None else fallback_day
    last_day = calendar.monthrange(due_month.year, due_month.month)[1]
    return date(due_month.year, due_month.month, min(requested_day, last_day))


def _generate_rule_periods(
    rule: RecurringRule,
    range_start: date,
    range_end: date,
) -> list[tuple[date, date, date]]:
    if (
        rule.end_date is not None and rule.end_date < range_start
    ) or rule.start_date > range_end:
        return []

    period_months = rule.period_months
    anchor_index = _month_index(rule.start_date)
    first_range_index = _month_index(range_start)
    last_range_index = _month_index(range_end)
    first_block = max(0, (first_range_index - anchor_index) // period_months)
    block_start_index = anchor_index + first_block * period_months

    periods = []
    while block_start_index <= last_range_index:
        block_end_index = block_start_index + period_months - 1
        period_start = max(_month_start(block_start_index), rule.start_date)
        period_end = _month_end(block_end_index)
        if rule.end_date is not None:
            period_end = min(period_end, rule.end_date)
        if period_start <= range_end and period_end >= range_start:
            periods.append(
                (
                    period_start,
                    period_end,
                    _due_date(
                        period_end,
                        rule.due_day,
                        rule.day_of_month,
                        rule.due_month_offset,
                    ),
                )
            )
        if rule.end_date is not None and period_end >= rule.end_date:
            break
        block_start_index += period_months

    return periods


async def get_obligation_statuses(
    session: AsyncSession,
    user_id: int,
    today: date,
    months_back: int = 3,
    months_forward: int = 2,
) -> list[ExpectedObligationPeriod]:
    range_start = _month_start(_month_index(today) - max(0, months_back))
    range_end = _month_end(_month_index(today) + max(0, months_forward))

    rules_result = await session.execute(
        select(RecurringRule).where(
            RecurringRule.user_id == user_id,
            RecurringRule.active.is_(True),
            RecurringRule.payment_behavior.in_(("manual_pay", "reserve_only")),
            RecurringRule.start_date <= range_end,
            (RecurringRule.end_date.is_(None) | (RecurringRule.end_date >= range_start)),
        )
    )
    rules = list(rules_result.scalars().all())
    if not rules:
        return []

    payments_result = await session.execute(
        select(ObligationPayment).where(
            ObligationPayment.user_id == user_id,
            ObligationPayment.recurring_rule_id.in_([rule.id for rule in rules]),
            ObligationPayment.status == "paid",
        )
    )
    payments = {
        (
            payment.recurring_rule_id,
            payment.period_start,
            payment.period_end,
        ): payment
        for payment in payments_result.scalars().all()
    }

    statuses = []
    for rule in rules:
        for period_start, period_end, due_date in _generate_rule_periods(
            rule,
            range_start,
            range_end,
        ):
            payment = payments.get((rule.id, period_start, period_end))
            status: ObligationStatus
            if payment is not None:
                status = "paid"
            elif today > due_date:
                status = "overdue"
            else:
                status = "unpaid"
            statuses.append(
                ExpectedObligationPeriod(
                    rule_id=rule.id,
                    description=rule.description,
                    obligation_type=rule.obligation_type,
                    payment_behavior=rule.payment_behavior,
                    period_start=period_start,
                    period_end=period_end,
                    due_date=due_date,
                    status=status,
                    amount=rule.amount,
                    currency=rule.currency,
                    transaction_id=(
                        payment.transaction_id if payment is not None else None
                    ),
                )
            )

    return sorted(statuses, key=lambda item: (item.due_date, item.rule_id))
