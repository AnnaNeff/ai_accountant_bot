import asyncio
import re
from datetime import date
from decimal import Decimal

import pytest

from app.models.financial_profile import FinancialProfile
from app.models.transaction import Transaction
from app.services.vat_report_service import (
    VATReportFinancialProfileNotFoundError,
    get_vat_report,
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
                and transaction.vat_relevant is True
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
    }
    data.update(overrides)
    return FinancialProfile(**data)


def make_transaction(**overrides: object) -> Transaction:
    data = {
        "user_id": 1,
        "type": "income",
        "amount": Decimal("118.00"),
        "amount_total": Decimal("118.00"),
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


def report_for(
    transactions: list[Transaction],
    profile: FinancialProfile | None = None,
):
    session = FakeSession(profile or make_profile(), transactions)
    report = asyncio.run(
        get_vat_report(
            session,  # type: ignore[arg-type]
            user_id=1,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 6, 30),
        )
    )
    return report, session


def test_osek_patur_returns_not_applicable_note_without_transaction_query() -> None:
    report, session = report_for([], make_profile(business_type="osek_patur"))

    assert report.vat_payable == Decimal("0.00")
    assert report.notes == ["VAT report is not applicable for osek_patur profile."]
    assert len(session.statements) == 1


def test_unknown_business_type_returns_warning_without_transaction_query() -> None:
    report, session = report_for([], make_profile(business_type="unknown"))

    assert report.vat_payable == Decimal("0.00")
    assert report.notes == [
        "Business type is unknown. Set business_type in financial profile."
    ]
    assert len(session.statements) == 1


def test_vat_report_requires_financial_profile() -> None:
    session = FakeSession(None)

    with pytest.raises(VATReportFinancialProfileNotFoundError, match="user_id=1"):
        asyncio.run(
            get_vat_report(
                session,  # type: ignore[arg-type]
                user_id=1,
                period_start=date(2026, 5, 1),
                period_end=date(2026, 6, 30),
            )
        )

    assert len(session.statements) == 1
    assert session.write_calls == []


def test_osek_murshe_includes_only_confirmed_current_user_transactions() -> None:
    report, session = report_for(
        [
            make_transaction(),
            make_transaction(user_id=2, vat_amount=Decimal("180.00")),
            make_transaction(status="pending", vat_amount=Decimal("90.00")),
            make_transaction(date=date(2026, 4, 30), vat_amount=Decimal("45.00")),
        ]
    )

    assert report.vat_output == Decimal("18.00")
    assert report.transactions_count == 1
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.user_id = 1" in sql
    assert "transactions.status = 'confirmed'" in sql
    assert "transactions.date >= '2026-05-01'" in sql
    assert "transactions.date <= '2026-06-30'" in sql


def test_vat_report_excludes_irrelevant_and_non_business_transactions() -> None:
    transactions = [
        make_transaction(),
        make_transaction(vat_relevant=False, vat_amount=Decimal("90.00")),
    ]
    for impact_type in ("personal", "tax_payment", "transfer", "reserve_only"):
        transactions.append(
            make_transaction(
                balance_impact_type=impact_type,
                vat_amount=Decimal("90.00"),
            )
        )

    report, session = report_for(transactions)

    assert report.vat_output == Decimal("18.00")
    assert report.transactions_count == 1
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.vat_relevant IS true" in sql
    assert "transactions.balance_impact_type = 'business'" in sql


def test_income_uses_explicit_vat_and_amount_total() -> None:
    report, _ = report_for(
        [
            make_transaction(
                amount=Decimal("120.00"),
                amount_total=Decimal("236.00"),
                vat_amount=Decimal("36.00"),
            )
        ]
    )

    assert report.income_total == Decimal("236.00")
    assert report.vat_output == Decimal("36.00")
    assert report.included_income_count == 1


def test_income_calculates_vat_from_gross_and_rate() -> None:
    report, _ = report_for(
        [
            make_transaction(
                amount=Decimal("118.00"),
                amount_total=None,
                vat_amount=None,
                vat_rate=Decimal("0.18"),
            )
        ]
    )

    assert report.income_total == Decimal("118.00")
    assert report.vat_output == Decimal("18.00")


def test_expense_vat_uses_business_percent_and_allows_null_deductibility() -> None:
    report, _ = report_for(
        [
            make_transaction(
                type="expense",
                amount_total=Decimal("118.00"),
                vat_amount=Decimal("18.00"),
                business_use_percent=Decimal("50.00"),
                tax_deductible=None,
            )
        ]
    )

    assert report.expense_total == Decimal("118.00")
    assert report.vat_input == Decimal("9.00")
    assert report.included_expense_count == 1


def test_expense_can_calculate_vat_from_gross_and_rate() -> None:
    report, _ = report_for(
        [
            make_transaction(
                type="expense",
                amount=Decimal("236.00"),
                amount_total=None,
                vat_amount=None,
                vat_rate=Decimal("0.18"),
            )
        ]
    )

    assert report.expense_total == Decimal("236.00")
    assert report.vat_input == Decimal("36.00")


def test_expense_tax_deductible_false_is_excluded_from_vat_input() -> None:
    report, _ = report_for(
        [
            make_transaction(
                type="expense",
                vat_amount=Decimal("18.00"),
                tax_deductible=False,
            )
        ]
    )

    assert report.expense_total == Decimal("118.00")
    assert report.vat_input == Decimal("0.00")
    assert report.included_expense_count == 1
    assert report.transactions_count == 1
    assert report.skipped_count == 0


def test_skipped_count_increments_when_vat_data_is_missing() -> None:
    report, _ = report_for(
        [
            make_transaction(vat_amount=None, vat_rate=None),
            make_transaction(
                type="expense",
                vat_amount=None,
                vat_rate=None,
            ),
        ]
    )

    assert report.transactions_count == 0
    assert report.skipped_count == 2


def test_vat_payable_can_be_negative() -> None:
    report, _ = report_for(
        [
            make_transaction(vat_amount=Decimal("18.00")),
            make_transaction(
                type="expense",
                amount=Decimal("236.00"),
                amount_total=Decimal("236.00"),
                vat_amount=Decimal("36.00"),
            ),
        ]
    )

    assert report.vat_payable == Decimal("-18.00")


def test_vat_report_is_read_only() -> None:
    report, session = report_for([make_transaction()])

    assert report.transactions_count == 1
    assert session.write_calls == []
