from pathlib import Path
from decimal import Decimal

from scripts.load_bootstrap import parse_bootstrap_data, read_bootstrap_file


def test_bootstrap_example_yaml_can_be_parsed() -> None:
    raw_data = read_bootstrap_file(Path("config/bootstrap.example.yaml"))
    data = parse_bootstrap_data(raw_data)

    assert data.owner.telegram_user_id == 123456789
    assert data.owner.name == "Anna"
    assert data.financial_profile.currency == "ILS"
    assert data.financial_profile.opening_balance_date.isoformat() == "2026-05-01"
    assert data.financial_profile.business_type == "osek_patur"
    assert data.financial_profile.tax_country == "IL"
    assert data.financial_profile.default_vat_rate is None
    assert data.financial_profile.income_tax_reserve_percent == Decimal("0.10")
    assert data.financial_profile.bituach_leumi_reserve_percent == Decimal("0.12")
    assert [rule.type for rule in data.recurring_rules] == [
        "income",
        "expense",
        "expense",
    ]
    assert [rule.frequency for rule in data.recurring_rules] == [
        "monthly",
        "monthly",
        "monthly",
    ]


def test_bootstrap_financial_profile_new_fields_are_optional() -> None:
    data = parse_bootstrap_data(
        {
            "owner": {"telegram_user_id": 123456789, "name": "Anna"},
            "financial_profile": {
                "opening_balance": "10000.00",
                "currency": "ILS",
                "opening_balance_date": "2026-05-01",
            },
        }
    )

    assert data.financial_profile.business_type == "unknown"
    assert data.financial_profile.tax_country == "IL"
    assert data.financial_profile.default_vat_rate is None
    assert data.financial_profile.income_tax_reserve_percent is None
    assert data.financial_profile.bituach_leumi_reserve_percent is None
