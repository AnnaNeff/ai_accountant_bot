import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.bituach_leumi import BituachLeumiReserveSummary
from app.schemas.income_tax import IncomeTaxReserveSummary
from app.schemas.vat import VATReportSummary
from app.services import tax_summary_service
from app.services.tax_summary_service import (
    PLANNING_DISCLAIMER,
    TaxSummaryFinancialProfileNotFoundError,
    get_tax_summary,
)
from app.services.vat_report_service import VATReportFinancialProfileNotFoundError

PERIOD_START = date(2026, 5, 1)
PERIOD_END = date(2026, 6, 30)


def make_vat_report(**overrides: object) -> VATReportSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "expense_total": Decimal("2000.00"),
        "vat_output": Decimal("1800.00"),
        "vat_input": Decimal("360.00"),
        "vat_payable": Decimal("1440.00"),
        "transactions_count": 2,
        "included_income_count": 1,
        "included_expense_count": 1,
        "skipped_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return VATReportSummary(**data)


def make_income_tax(**overrides: object) -> IncomeTaxReserveSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "deductible_expense_total": Decimal("2000.00"),
        "taxable_profit": Decimal("8000.00"),
        "reserve_percent": Decimal("0.10"),
        "estimated_income_tax_reserve": Decimal("800.00"),
        "transactions_count": 2,
        "included_income_count": 1,
        "included_expense_count": 1,
        "skipped_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return IncomeTaxReserveSummary(**data)


def make_bituach_leumi(**overrides: object) -> BituachLeumiReserveSummary:
    data = {
        "business_type": "osek_murshe",
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "currency": "ILS",
        "income_total": Decimal("10000.00"),
        "deductible_expense_total": Decimal("2000.00"),
        "estimated_profit": Decimal("8000.00"),
        "reserve_percent": Decimal("0.12"),
        "estimated_bituach_leumi_reserve": Decimal("960.00"),
        "transactions_count": 2,
        "included_income_count": 1,
        "included_expense_count": 1,
        "skipped_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return BituachLeumiReserveSummary(**data)


class ReadOnlySession:
    def __init__(self) -> None:
        self.write_calls: list[str] = []
        self.transactions = ["existing transaction"]
        self.obligation_payments = ["existing obligation payment"]
        self.balance = Decimal("5000.00")

    def add(self, item: object) -> None:
        self.write_calls.append("add")

    async def flush(self) -> None:
        self.write_calls.append("flush")

    async def commit(self) -> None:
        self.write_calls.append("commit")


def run_summary(
    monkeypatch: pytest.MonkeyPatch,
    vat_report: VATReportSummary | None = None,
    income_tax: IncomeTaxReserveSummary | None = None,
    bituach_leumi: BituachLeumiReserveSummary | None = None,
):
    calls: list[tuple[str, object, int, date, date]] = []

    async def fake_vat(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> VATReportSummary:
        calls.append(("vat", session, user_id, period_start, period_end))
        return vat_report or make_vat_report()

    async def fake_income_tax(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> IncomeTaxReserveSummary:
        calls.append(("income_tax", session, user_id, period_start, period_end))
        return income_tax or make_income_tax()

    async def fake_bituach_leumi(
        session: object,
        user_id: int,
        period_start: date,
        period_end: date,
    ) -> BituachLeumiReserveSummary:
        calls.append(("bituach_leumi", session, user_id, period_start, period_end))
        return bituach_leumi or make_bituach_leumi()

    monkeypatch.setattr(tax_summary_service, "get_vat_report", fake_vat)
    monkeypatch.setattr(
        tax_summary_service,
        "get_income_tax_reserve",
        fake_income_tax,
    )
    monkeypatch.setattr(
        tax_summary_service,
        "get_bituach_leumi_reserve",
        fake_bituach_leumi,
    )

    session = ReadOnlySession()
    summary = asyncio.run(
        get_tax_summary(
            session,  # type: ignore[arg-type]
            user_id=7,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )
    )
    return summary, calls, session


def test_tax_summary_reuses_existing_service_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary, calls, session = run_summary(monkeypatch)

    assert [call[0] for call in calls] == ["vat", "income_tax", "bituach_leumi"]
    assert all(call[1:] == (session, 7, PERIOD_START, PERIOD_END) for call in calls)
    assert summary.vat_payable == Decimal("1440.00")
    assert summary.income_tax_reserve == Decimal("800.00")
    assert summary.bituach_leumi_reserve == Decimal("960.00")
    assert session.write_calls == []


def test_osek_murshe_sums_all_reserves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary, _, _ = run_summary(monkeypatch)

    assert summary.total_estimated_tax_reserve == Decimal("3200.00")
    assert summary.vat_applicable is True
    assert summary.income_tax_configured is True
    assert summary.bituach_leumi_configured is True
    assert summary.notes == [PLANNING_DISCLAIMER]


def test_tax_summary_does_not_create_records_or_change_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, session = run_summary(monkeypatch)

    assert session.transactions == ["existing transaction"]
    assert session.obligation_payments == ["existing obligation payment"]
    assert session.balance == Decimal("5000.00")
    assert session.write_calls == []


def test_osek_patur_has_zero_vat_and_not_applicable_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = "VAT report is not applicable for osek_patur profile."
    summary, _, _ = run_summary(
        monkeypatch,
        vat_report=make_vat_report(
            business_type="osek_patur",
            vat_payable=Decimal("0.00"),
            notes=[note],
        ),
        income_tax=make_income_tax(business_type="osek_patur"),
        bituach_leumi=make_bituach_leumi(business_type="osek_patur"),
    )

    assert summary.business_type == "osek_patur"
    assert summary.vat_payable == Decimal("0.00")
    assert summary.vat_applicable is False
    assert summary.total_estimated_tax_reserve == Decimal("1760.00")
    assert note in summary.notes


def test_unknown_business_type_does_not_crash_and_combines_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary, _, _ = run_summary(
        monkeypatch,
        vat_report=make_vat_report(
            business_type="unknown",
            vat_payable=Decimal("0.00"),
            notes=[
                "Business type is unknown. Set business_type in financial profile."
            ],
        ),
        income_tax=make_income_tax(
            business_type="unknown",
            notes=["Income tax used configured reserve percent."],
        ),
        bituach_leumi=make_bituach_leumi(
            business_type="unknown",
            notes=["Bituach Leumi used configured reserve percent."],
        ),
    )

    assert summary.business_type == "unknown"
    assert summary.vat_payable == Decimal("0.00")
    assert summary.total_estimated_tax_reserve == Decimal("1760.00")
    assert len(summary.notes) == 4
    assert summary.notes[-1] == PLANNING_DISCLAIMER


def test_negative_vat_does_not_reduce_total_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary, _, _ = run_summary(
        monkeypatch,
        vat_report=make_vat_report(vat_payable=Decimal("-250.00")),
    )

    assert summary.vat_payable == Decimal("-250.00")
    assert summary.total_estimated_tax_reserve == Decimal("1760.00")


def test_missing_income_tax_percent_gives_zero_and_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = "Income tax reserve percent is not set in financial profile."
    summary, _, _ = run_summary(
        monkeypatch,
        income_tax=make_income_tax(
            reserve_percent=None,
            estimated_income_tax_reserve=Decimal("0.00"),
            notes=[note],
        ),
    )

    assert summary.income_tax_reserve == Decimal("0.00")
    assert summary.income_tax_configured is False
    assert note in summary.notes


def test_missing_bituach_leumi_percent_gives_zero_and_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = "Bituach Leumi reserve percent is not set in financial profile."
    summary, _, _ = run_summary(
        monkeypatch,
        bituach_leumi=make_bituach_leumi(
            reserve_percent=None,
            estimated_bituach_leumi_reserve=Decimal("0.00"),
            notes=[note],
        ),
    )

    assert summary.bituach_leumi_reserve == Decimal("0.00")
    assert summary.bituach_leumi_configured is False
    assert note in summary.notes


def test_missing_profile_is_exposed_as_tax_summary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_profile(*args: object, **kwargs: object) -> VATReportSummary:
        raise VATReportFinancialProfileNotFoundError("missing")

    monkeypatch.setattr(tax_summary_service, "get_vat_report", missing_profile)

    with pytest.raises(TaxSummaryFinancialProfileNotFoundError, match="missing"):
        asyncio.run(
            get_tax_summary(
                ReadOnlySession(),  # type: ignore[arg-type]
                user_id=7,
                period_start=PERIOD_START,
                period_end=PERIOD_END,
            )
        )
