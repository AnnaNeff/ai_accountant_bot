from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate

UPDATABLE_TRANSACTION_TAX_FIELDS = {
    "amount_total",
    "amount_net",
    "vat_amount",
    "vat_rate",
    "vat_included",
    "vat_relevant",
    "business_use_percent",
    "tax_deductible",
    "tax_category",
    "balance_impact_type",
}
DECIMAL_TRANSACTION_TAX_FIELD_RANGES = {
    "amount_total": (Decimal("0"), None),
    "amount_net": (Decimal("0"), None),
    "vat_amount": (Decimal("0"), None),
    "vat_rate": (Decimal("0"), Decimal("1")),
    "business_use_percent": (Decimal("0"), Decimal("100")),
}
BOOLEAN_TRANSACTION_TAX_FIELDS = {
    "vat_included",
    "vat_relevant",
    "tax_deductible",
}
BALANCE_IMPACT_TYPES = {
    "business",
    "personal",
    "tax_payment",
    "transfer",
    "reserve_only",
}


def validate_transaction_tax_field_value(field: str, value: Any) -> None:
    if field not in UPDATABLE_TRANSACTION_TAX_FIELDS:
        raise ValueError("Unsupported transaction tax field.")

    if field in DECIMAL_TRANSACTION_TAX_FIELD_RANGES:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("Invalid transaction tax field value.")
        minimum, maximum = DECIMAL_TRANSACTION_TAX_FIELD_RANGES[field]
        if value < minimum or maximum is not None and value > maximum:
            raise ValueError("Invalid transaction tax field value.")
    elif field in BOOLEAN_TRANSACTION_TAX_FIELDS:
        if not isinstance(value, bool):
            raise ValueError("Invalid transaction tax field value.")
    elif field == "tax_category":
        if value is not None and (
            not isinstance(value, str) or not value or len(value) > 255
        ):
            raise ValueError("Invalid transaction tax field value.")
    elif field == "balance_impact_type" and value not in BALANCE_IMPACT_TYPES:
        raise ValueError("Invalid transaction tax field value.")


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


async def get_transaction_by_id(
    session: AsyncSession,
    user_id: int,
    transaction_id: int,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_transaction_tax_field(
    session: AsyncSession,
    user_id: int,
    transaction_id: int,
    field: str,
    value: Any,
) -> Transaction | None:
    validate_transaction_tax_field_value(field, value)

    transaction = await get_transaction_by_id(
        session,
        user_id=user_id,
        transaction_id=transaction_id,
    )
    if transaction is None:
        return None

    setattr(transaction, field, value)
    await session.commit()
    await session.refresh(transaction)
    return transaction


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
