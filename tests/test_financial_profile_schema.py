from datetime import date
from decimal import Decimal

import pytest

from app.schemas.financial_profile import FinancialProfileCreate


def test_financial_profile_validates_business_type() -> None:
    with pytest.raises(ValueError):
        FinancialProfileCreate(
            opening_balance_date=date(2026, 5, 1),
            business_type="company",  # type: ignore[arg-type]
        )


def test_financial_profile_accepts_supported_business_types() -> None:
    patur = FinancialProfileCreate(
        opening_balance_date=date(2026, 5, 1),
        business_type="osek_patur",
    )
    murshe = FinancialProfileCreate(
        opening_balance_date=date(2026, 5, 1),
        business_type="osek_murshe",
        default_vat_rate=Decimal("0.1800"),
    )

    assert patur.business_type == "osek_patur"
    assert patur.tax_country == "IL"
    assert patur.default_vat_rate is None
    assert murshe.business_type == "osek_murshe"
    assert murshe.default_vat_rate == Decimal("0.1800")


def test_financial_profile_validates_percent_ranges() -> None:
    with pytest.raises(ValueError, match="Percent values must be between 0 and 1"):
        FinancialProfileCreate(
            opening_balance_date=date(2026, 5, 1),
            default_vat_rate=Decimal("1.01"),
        )
