from pathlib import Path

import pytesseract
from PIL import Image


def extract_text_from_image(
    image_path: Path,
    languages: str = "eng",
) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with Image.open(image_path) as image:
        text = pytesseract.image_to_string(image, lang=languages)

    return text.strip()
