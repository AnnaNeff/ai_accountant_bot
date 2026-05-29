import hashlib
from datetime import date
from pathlib import Path
from uuid import uuid4


def ensure_storage_dir(base_path: str) -> None:
    Path(base_path).mkdir(parents=True, exist_ok=True)


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_document_path(
    base_path: str,
    user_id: int,
    original_extension: str = ".jpg",
) -> Path:
    today = date.today()
    extension = (
        original_extension
        if original_extension.startswith(".")
        else f".{original_extension}"
    )
    return (
        Path(base_path)
        / str(user_id)
        / f"{today:%Y}"
        / f"{today:%m}"
        / f"{uuid4()}{extension}"
    )
