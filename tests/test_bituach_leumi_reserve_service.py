import asyncio
import re
from datetime import date
from decimal import Decimal

import pytest

from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.services.bituach_leumi_reserve_service import (
    BituachLeumiReserveFinancialProfileNotFoundError,
    get_bituach_leumi_reserve,
)


class FakeScalarResult:
    def __init__(self, items: list[Transaction]) -> None:
        self.items = items

    def all(self) -> list[Transaction]:
        return self.items


class FakeProfileResult:
    def __init__(self, profile: FinancialProfile | None) -> None:
        self.profile = profile

    def scalar_one_or_none(self) -> FinancialProfile | None:
        return self.profile


class FakeTransactionsResult:
    def __init__(self, transactions: list[Transaction]) -> None:
        self.transactions = transactions

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.transactions)


class FakeSession:
    def __init__(
        self,
        profile: FinancialProfile | None,
        transactions: list[Transaction] | None = None,
    ) -> None:
        self.profile = profile
        self.transactions = transactions or []
        self.statements: list[object] = []
        self.write_calls: list[str] = []

    async def execute(self, statement: object) -> object:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return FakeProfileResult(self.profile)

        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        user_id_match = re.search(r"transactions\.user_id = (\d+)", sql)
        start_match = re.search(r"transactions\.date >= '([^']+)'", sql)
        end_match = re.search(r"transactions\.date <= '([^']+)'", sql)
        user_id = int(user_id_match.group(1)) if user_id_match else -1
        period_start = date.fromisoformat(start_match.group(1)) if start_match else date.min
        period_end = date.fromisoformat(end_match.group(1)) if end_match else date.max

        return FakeTransactionsResult(
            [
                transaction
                for transaction in self.transactions
                if transaction.user_id == user_id
                and transaction.status == "confirmed"
                and period_start <= transaction.date <= period_end
                and transaction.balance_impact_type == "business"
                and transaction.type in {"income", "expense"}
            ]
        )

    def add(self, item: object) -> None:
        self.write_calls.append("add")

    async def commit(self) -> None:
        self.write_calls.append("commit")

    async def flush(self) -> None:
        self.write_calls.append("flush")


def make_profile(**overrides: object) -> FinancialProfile:
    data = {
        "user_id": 1,
        "opening_balance": Decimal("0.00"),
        "currency": "ILS",
        "opening_balance_date": date(2026, 1, 1),
        "business_type": "osek_murshe",
        "bituach_leumi_reserve_percent": Decimal("0.12"),
    }
    data.update(overrides)
    return FinancialProfile(**data)


def make_transaction(**overrides: object) -> Transaction:
    data = {
        "user_id": 1,
        "type": "income",
        "amount": Decimal("118.00"),
        "amount_total": Decimal("118.00"),
        "amount_net": None,
        "vat_amount": Decimal("18.00"),
        "vat_rate": Decimal("0.18"),
        "vat_relevant": True,
        "business_use_percent": Decimal("100.00"),
        "tax_deductible": None,
        "balance_impact_type": "business",
        "currency": "ILS",
        "date": date(2026, 5, 15),
        "source": "manual",
        "status": "confirmed",
    }
    data.update(overrides)
    return Transaction(**data)


def reserve_for(
    transactions: list[Transaction],
    profile: FinancialProfile | None = None,
):
    session = FakeSession(profile or make_profile(), transactions)
    summary = asyncio.run(
        get_bituach_leumi_reserve(
            session,  # type: ignore[arg-type]
            user_id=1,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 6, 30),
        )
    )
    return summary, session


def test_bituach_leumi_reserve_requires_financial_profile() -> None:
    session = FakeSession(None)

    with pytest.raises(
        BituachLeumiReserveFinancialProfileNotFoundError,
        match="user_id=1",
    ):
        asyncio.run(
            get_bituach_leumi_reserve(
                session,  # type: ignore[arg-type]
                user_id=1,
                period_start=date(2026, 5, 1),
                period_end=date(2026, 6, 30),
            )
        )

    assert session.write_calls == []


def test_missing_percent_returns_note_and_zero_without_transaction_query() -> None:
    summary, session = reserve_for(
        [make_transaction()],
        make_profile(bituach_leumi_reserve_percent=None),
    )

    assert summary.reserve_percent is None
    assert summary.estimated_bituach_leumi_reserve == Decimal("0.00")
    assert summary.notes == [
        "Bituach Leumi reserve percent is not set in financial profile."
    ]
    assert len(session.statements) == 1


def test_unknown_business_type_can_calculate_and_adds_note() -> None:
    summary, _ = reserve_for(
        [make_transaction(amount_net=Decimal("1000.00"))],
        make_profile(business_type="unknown"),
    )

    assert summary.estimated_bituach_leumi_reserve == Decimal("120.00")
    assert summary.notes == [
        "Business type is unknown. Reserve is based only on configured "
        "bituach_leumi_reserve_percent."
    ]


@pytest.mark.parametrize("business_type", ["osek_patur", "osek_murshe"])
def test_supported_business_types_can_calculate_reserve(business_type: str) -> None:
    summary, _ = reserve_for(
        [make_transaction(amount_net=Decimal("1000.00"))],
        make_profile(business_type=business_type),
    )

    assert summary.business_type == business_type
    assert summary.estimated_bituach_leumi_reserve == Decimal("120.00")


def test_includes_only_confirmed_current_user_transactions_and_boundaries() -> None:
    summary, session = reserve_for(
        [
            make_transaction(date=date(2026, 5, 1), amount_net=Decimal("100.00")),
            make_transaction(date=date(2026, 6, 30), amount_net=Decimal("200.00")),
            make_transaction(user_id=2, amount_net=Decimal("900.00")),
            make_transaction(status="pending", amount_net=Decimal("800.00")),
            make_transaction(date=date(2026, 4, 30), amount_net=Decimal("700.00")),
        ]
    )

    assert summary.income_total == Decimal("300.00")
    assert summary.transactions_count == 2
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.user_id = 1" in sql
    assert "transactions.status = 'confirmed'" in sql
    assert "transactions.date >= '2026-05-01'" in sql
    assert "transactions.date <= '2026-06-30'" in sql


def test_excludes_non_business_balance_impact_types() -> None:
    transactions = [make_transaction(amount_net=Decimal("100.00"))]
    for impact_type in ("personal", "tax_payment", "transfer", "reserve_only"):
        transactions.append(
            make_transaction(
                amount_net=Decimal("900.00"),
                balance_impact_type=impact_type,
            )
        )

    summary, session = reserve_for(transactions)

    assert summary.income_total == Decimal("100.00")
    assert summary.transactions_count == 1
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.balance_impact_type = 'business'" in sql


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "amount": Decimal("500.00"),
                "amount_total": Decimal("1180.00"),
                "amount_net": Decimal("900.00"),
                "vat_amount": Decimal("180.00"),
            },
            Decimal("900.00"),
        ),
        (
            {
                "amount_total": Decimal("1180.00"),
                "amount_net": None,
                "vat_amount": Decimal("180.00"),
            },
            Decimal("1000.00"),
        ),
        (
            {
                "amount": Decimal("10.00"),
                "amount_total": Decimal("250.00"),
                "amount_net": None,
                "vat_amount": None,
            },
            Decimal("250.00"),
        ),
        (
            {
                "amount": Decimal("75.00"),
                "amount_total": None,
                "amount_net": None,
                "vat_amount": None,
            },
            Decimal("75.00"),
        ),
    ],
)
def test_income_amount_priority(
    overrides: dict[str, object],
    expected: Decimal,
) -> None:
    summary, _ = reserve_for([make_transaction(**overrides)])

    assert summary.income_total == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "amount_total": Decimal("590.00"),
                "amount_net": Decimal("400.00"),
                "vat_amount": Decimal("90.00"),
            },
            Decimal("400.00"),
        ),
        (
            {
                "amount_total": Decimal("590.00"),
                "amount_net": None,
                "vat_amount": Decimal("90.00"),
            },
            Decimal("500.00"),
        ),
        (
            {
                "amount": Decimal("10.00"),
                "amount_total": Decimal("250.00"),
                "amount_net": None,
                "vat_amount": None,
            },
            Decimal("250.00"),
        ),
        (
            {
                "amount": Decimal("75.00"),
                "amount_total": None,
                "amount_net": None,
                "vat_amount": None,
            },
            Decimal("75.00"),
        ),
    ],
)
def test_expense_amount_priority(
    overrides: dict[str, object],
    expected: Decimal,
) -> None:
    summary, _ = reserve_for(
        [make_transaction(type="expense", **overrides)]
    )

    assert summary.deductible_expense_total == expected


def test_business_use_percent_reduces_deductible_expense() -> None:
    summary, _ = reserve_for(
        [
            make_transaction(
                type="expense",
                amount_net=Decimal("500.00"),
                business_use_percent=Decimal("40.00"),
            )
        ]
    )

    assert summary.deductible_expense_total == Decimal("200.00")


@pytest.mark.parametrize("tax_deductible", [True, None])
def test_true_or_null_deductibility_includes_expense(
    tax_deductible: bool | None,
) -> None:
    summary, _ = reserve_for(
        [
            make_transaction(
                type="expense",
                amount_net=Decimal("500.00"),
                tax_deductible=tax_deductible,
            )
        ]
    )

    assert summary.deductible_expense_total == Decimal("500.00")


def test_non_deductible_expense_is_processed_but_not_deducted() -> None:
    summary, _ = reserve_for(
        [
            make_transaction(
                type="expense",
                amount_net=Decimal("500.00"),
                tax_deductible=False,
            )
        ]
    )

    assert summary.deductible_expense_total == Decimal("0.00")
    assert summary.included_expense_count == 1
    assert summary.transactions_count == 1
    assert summary.skipped_count == 0


def test_non_positive_profit_gives_zero_reserve_and_note() -> None:
    summary, _ = reserve_for(
        [
            make_transaction(type="income", amount_net=Decimal("500.00")),
            make_transaction(type="expense", amount_net=Decimal("700.00")),
        ]
    )

    assert summary.estimated_profit == Decimal("-200.00")
    assert summary.estimated_bituach_leumi_reserve == Decimal("0.00")
    assert "No positive estimated profit for this period." in summary.notes


def test_positive_profit_uses_configured_percent() -> None:
    summary, _ = reserve_for(
        [
            make_transaction(type="income", amount_net=Decimal("10000.00")),
            make_transaction(type="expense", amount_net=Decimal("2000.00")),
        ]
    )

    assert summary.estimated_profit == Decimal("8000.00")
    assert summary.estimated_bituach_leumi_reserve == Decimal("960.00")
    assert summary.transactions_count == 2


def test_money_values_are_rounded_to_two_decimals() -> None:
    summary, _ = reserve_for(
        [
            make_transaction(type="income", amount_net=Decimal("100.005")),
            make_transaction(
                type="expense",
                amount_net=Decimal("33.335"),
                business_use_percent=Decimal("50.00"),
            ),
        ],
        make_profile(bituach_leumi_reserve_percent=Decimal("0.1234")),
    )

    assert summary.income_total == Decimal("100.01")
    assert summary.deductible_expense_total == Decimal("16.67")
    assert summary.estimated_profit == Decimal("83.34")
    assert summary.estimated_bituach_leumi_reserve == Decimal("10.28")
    for value in (
        summary.income_total,
        summary.deductible_expense_total,
        summary.estimated_profit,
        summary.estimated_bituach_leumi_reserve,
    ):
        assert value.as_tuple().exponent == -2


def test_bituach_leumi_reserve_is_read_only() -> None:
    summary, session = reserve_for([make_transaction()])

    assert summary.transactions_count == 1
    assert session.write_calls == []
