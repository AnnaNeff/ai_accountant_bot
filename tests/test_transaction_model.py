from app.db.base import Base


def test_transaction_table_is_registered_with_required_indexes() -> None:
    table = Base.metadata.tables["transactions"]

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "type",
        "date",
        "amount",
        "currency",
        "category",
        "description",
        "source",
        "status",
        "created_at",
        "updated_at",
    }
    assert next(iter(table.c.user_id.foreign_keys)).target_fullname == "users.id"
    assert {index.name for index in table.indexes} == {
        "ix_transactions_user_id",
        "ix_transactions_date",
        "ix_transactions_type",
    }
