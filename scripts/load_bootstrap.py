from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.recurring_rule import RecurringRule
from app.schemas.financial_profile import FinancialProfileCreate
from app.schemas.recurring_rule import RecurringRuleCreate


class BootstrapError(Exception):
    pass


class OwnerBootstrap(BaseModel):
    telegram_user_id: int
    name: str | None = None


@dataclass(frozen=True)
class BootstrapData:
    owner: OwnerBootstrap
    financial_profile: FinancialProfileCreate
    recurring_rules: list[RecurringRuleCreate]


def read_bootstrap_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BootstrapError(f"Bootstrap file not found: {path}")

    with path.open(encoding="utf-8") as file:
        raw_data = yaml.safe_load(file)

    if not isinstance(raw_data, dict):
        raise BootstrapError("Bootstrap YAML must contain a mapping at the top level.")

    return raw_data


def parse_bootstrap_data(raw_data: dict[str, Any]) -> BootstrapData:
    try:
        owner = OwnerBootstrap.model_validate(raw_data["owner"])
        financial_profile = FinancialProfileCreate.model_validate(
            raw_data["financial_profile"]
        )
        recurring_rules = [
            *_parse_rule_list(
                raw_data.get("regular_income", []),
                "income",
                financial_profile.opening_balance_date,
            ),
            *_parse_rule_list(
                raw_data.get("regular_expenses", []),
                "expense",
                financial_profile.opening_balance_date,
            ),
        ]
    except KeyError as error:
        raise BootstrapError(f"Missing required field: {error.args[0]}") from error
    except ValidationError as error:
        raise BootstrapError(f"Invalid bootstrap data: {error}") from error

    return BootstrapData(
        owner=owner,
        financial_profile=financial_profile,
        recurring_rules=recurring_rules,
    )


def _parse_rule_list(
    items: Any,
    rule_type: str,
    default_start_date: object,
) -> list[RecurringRuleCreate]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise BootstrapError(f"{rule_type} recurring rules must be a list.")

    rules = []
    for item in items:
        if not isinstance(item, Mapping):
            raise BootstrapError(f"{rule_type} recurring rule must be a mapping.")
        rules.append(
            RecurringRuleCreate.model_validate(
                {"start_date": default_start_date, **item, "type": rule_type}
            )
        )

    return rules


async def load_bootstrap(data: BootstrapData) -> None:
    from app.db.session import async_session_factory, engine
    from app.services.financial_profile_service import (
        create_or_update_financial_profile,
    )
    from app.services.user_service import get_or_create_user

    async with async_session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_user_id=data.owner.telegram_user_id,
            name=data.owner.name,
        )
        await create_or_update_financial_profile(
            session,
            user_id=user.id,
            data=data.financial_profile,
        )

        created_count = 0
        skipped_count = 0
        for rule_data in data.recurring_rules:
            was_created = await create_recurring_rule_if_missing(
                session,
                user_id=user.id,
                data=rule_data,
            )
            if was_created:
                created_count += 1
            else:
                skipped_count += 1

    await engine.dispose()
    print(
        "Bootstrap loaded: "
        f"user_id={user.id}, recurring_created={created_count}, "
        f"recurring_skipped={skipped_count}"
    )


async def create_recurring_rule_if_missing(
    session: AsyncSession,
    user_id: int,
    data: RecurringRuleCreate,
) -> bool:
    result = await session.execute(
        select(RecurringRule).where(
            RecurringRule.user_id == user_id,
            RecurringRule.type == data.type,
            RecurringRule.amount == data.amount,
            RecurringRule.currency == data.currency,
            RecurringRule.category == data.category,
            RecurringRule.description == data.description,
            RecurringRule.frequency == data.frequency,
            RecurringRule.day_of_month == data.day_of_month,
            RecurringRule.payment_behavior == data.payment_behavior,
            RecurringRule.obligation_type == data.obligation_type,
            RecurringRule.affects_balance_when_generated
            == data.affects_balance_when_generated,
            RecurringRule.start_date == data.start_date,
            RecurringRule.end_date == data.end_date,
        )
    )
    existing_rule = result.scalar_one_or_none()

    if existing_rule is not None:
        return False

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
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load bootstrap finance data.")
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to private bootstrap YAML file.",
    )
    return parser


async def async_main() -> int:
    args = build_parser().parse_args()
    try:
        raw_data = read_bootstrap_file(args.file)
        data = parse_bootstrap_data(raw_data)
        await load_bootstrap(data)
    except BootstrapError as error:
        print(f"Error: {error}")
        return 1

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
