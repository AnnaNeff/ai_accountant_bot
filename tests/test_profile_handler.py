from datetime import date
from decimal import Decimal

from app.bot.handlers.profile import format_financial_profile
from app.models.financial_profile import FinancialProfile


def test_format_financial_profile_shows_business_type() -> None:
    profile = FinancialProfile(
        user_id=1,
        opening_balance=Decimal("1000.00"),
        currency="ILS",
        opening_balance_date=date(2026, 5, 1),
        business_type="osek_patur",
        tax_country="IL",
        default_vat_rate=None,
        income_tax_reserve_percent=Decimal("0.1000"),
        bituach_leumi_reserve_percent=Decimal("0.1200"),
    )

    assert format_financial_profile(profile) == (
        "Financial profile:\n\n"
        "Opening balance: 1,000.00\n"
        "Currency: ILS\n"
        "Opening balance date: 2026-05-01\n"
        "Business type: osek_patur\n"
        "Tax country: IL\n"
        "Default VAT rate: not set\n"
        "Income tax reserve percent: 0.1000\n"
        "Bituach Leumi reserve percent: 0.1200"
    )
