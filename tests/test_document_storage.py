from datetime import date
from pathlib import Path

from app.storage.file_storage import build_document_path, calculate_sha256


def test_build_document_path_builds_path_inside_document_storage() -> None:
    base_path = "data/private/documents"
    user_id = 42

    document_path = build_document_path(base_path, user_id)

    today = date.today()
    relative_path = document_path.relative_to(Path(base_path))

    assert relative_path.parts[0:3] == (str(user_id), f"{today:%Y}", f"{today:%m}")
    assert document_path.suffix == ".jpg"
    assert document_path.is_relative_to(Path(base_path))


def test_calculate_sha256_returns_same_hash_for_same_file(tmp_path: Path) -> None:
    first_file = tmp_path / "first.jpg"
    second_file = tmp_path / "second.jpg"
    content = b"same document bytes"
    first_file.write_bytes(content)
    second_file.write_bytes(content)

    assert calculate_sha256(first_file) == calculate_sha256(second_file)
