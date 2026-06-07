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
        "expense",
        "expense",
    ]
    assert [rule.frequency for rule in data.recurring_rules] == [
        "monthly",
        "monthly",
        "monthly",
        "monthly",
        "monthly",
    ]
    assert [rule.payment_behavior for rule in data.recurring_rules] == [
        "auto_pay",
        "auto_pay",
        "auto_pay",
        "manual_pay",
        "manual_pay",
    ]
    assert [rule.obligation_type for rule in data.recurring_rules] == [
        "regular",
        "rent",
        "loan",
        "vat",
        "bituach_leumi",
    ]
    assert data.recurring_rules[3].period_months == 2
    assert data.recurring_rules[3].due_day == 15
    assert data.recurring_rules[3].due_month_offset == 1
    assert data.recurring_rules[4].period_months == 1
    assert data.recurring_rules[4].due_day == 15
    assert data.recurring_rules[4].due_month_offset == 0


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


def test_bootstrap_old_recurring_rules_get_obligation_defaults() -> None:
    data = parse_bootstrap_data(
        {
            "owner": {"telegram_user_id": 123456789, "name": "Anna"},
            "financial_profile": {
                "opening_balance": "10000.00",
                "currency": "ILS",
                "opening_balance_date": "2026-05-01",
            },
            "regular_expenses": [
                {
                    "description": "Rent",
                    "amount": "4500.00",
                    "currency": "ILS",
                    "frequency": "monthly",
                    "day_of_month": 1,
                    "category": "rent",
                }
            ],
        }
    )

    rule = data.recurring_rules[0]
    assert rule.payment_behavior == "auto_pay"
    assert rule.obligation_type == "regular"
    assert rule.affects_balance_when_generated is True
    assert rule.period_months == 1
    assert rule.due_day == 1
    assert rule.due_month_offset == 0
