from pathlib import Path

from scripts.load_bootstrap import parse_bootstrap_data, read_bootstrap_file


def test_bootstrap_example_yaml_can_be_parsed() -> None:
    raw_data = read_bootstrap_file(Path("config/bootstrap.example.yaml"))
    data = parse_bootstrap_data(raw_data)

    assert data.owner.telegram_user_id == 123456789
    assert data.owner.name == "Anna"
    assert data.financial_profile.currency == "ILS"
    assert data.financial_profile.opening_balance_date.isoformat() == "2026-05-01"
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
