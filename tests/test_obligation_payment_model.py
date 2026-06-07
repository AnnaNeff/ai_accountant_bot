from app.db.base import Base


def test_obligation_payment_table_is_registered_with_required_indexes() -> None:
    table = Base.metadata.tables["obligation_payments"]

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "recurring_rule_id",
        "transaction_id",
        "period_start",
        "period_end",
        "amount",
        "currency",
        "status",
        "notes",
        "created_at",
        "updated_at",
    }
    assert next(iter(table.c.user_id.foreign_keys)).target_fullname == "users.id"
    assert (
        next(iter(table.c.recurring_rule_id.foreign_keys)).target_fullname
        == "recurring_rules.id"
    )
    assert (
        next(iter(table.c.transaction_id.foreign_keys)).target_fullname
        == "transactions.id"
    )
    assert {index.name for index in table.indexes} == {
        "ix_obligation_payments_user_id",
        "ix_obligation_payments_recurring_rule_id",
        "ix_obligation_payments_transaction_id",
        "ix_obligation_payments_period_start",
        "ix_obligation_payments_period_end",
        "ix_obligation_payments_status",
    }
