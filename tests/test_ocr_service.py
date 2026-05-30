from pathlib import Path
from typing import Any

from app.ocr import ocr_service


class FakeImage:
    def __enter__(self) -> "FakeImage":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_extract_text_from_image_calls_tesseract_with_languages(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-image")
    fake_image = FakeImage()
    calls: dict[str, Any] = {}

    def fake_open(path: Path) -> FakeImage:
        calls["path"] = path
        return fake_image

    def fake_image_to_string(image: FakeImage, lang: str) -> str:
        calls["image"] = image
        calls["lang"] = lang
        return "  Milk\nBread  "

    monkeypatch.setattr(ocr_service.Image, "open", fake_open)
    monkeypatch.setattr(ocr_service.pytesseract, "image_to_string", fake_image_to_string)

    result = ocr_service.extract_text_from_image(image_path, languages="eng+heb")

    assert result == "Milk\nBread"
    assert calls == {"path": image_path, "image": fake_image, "lang": "eng+heb"}


def test_extract_text_from_image_returns_empty_cleaned_text(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "blank.jpg"
    image_path.write_bytes(b"fake-image")

    monkeypatch.setattr(ocr_service.Image, "open", lambda path: FakeImage())
    monkeypatch.setattr(ocr_service.pytesseract, "image_to_string", lambda image, lang: "  \n ")

    assert ocr_service.extract_text_from_image(image_path) == ""


def test_extract_text_from_image_missing_file_raises_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jpg"

    try:
        ocr_service.extract_text_from_image(missing_path)
    except FileNotFoundError as error:
        assert str(missing_path) in str(error)
    else:
        raise AssertionError("Expected FileNotFoundError")
