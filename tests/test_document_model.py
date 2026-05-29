from app.db.base import Base


def test_document_table_is_registered_with_required_indexes() -> None:
    table = Base.metadata.tables["documents"]

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "transaction_id",
        "telegram_file_id",
        "local_path",
        "file_hash",
        "mime_type",
        "file_size_bytes",
        "status",
        "created_at",
        "updated_at",
    }
    assert next(iter(table.c.user_id.foreign_keys)).target_fullname == "users.id"
    assert next(iter(table.c.transaction_id.foreign_keys)).target_fullname == "transactions.id"
    assert {index.name for index in table.indexes} == {
        "ix_documents_user_id",
        "ix_documents_transaction_id",
        "ix_documents_file_hash",
        "ix_documents_status",
    }
