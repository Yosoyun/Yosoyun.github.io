from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float | None
    engine: str
    source: str


def extract_text_from_image(path: str | Path, engine: str = "tesseract") -> OcrResult:
    """Extract text from an image using a local OCR engine.

    The default engine is intentionally simple and optional. Handwritten copies
    should eventually use a stronger adapter such as TrOCR/PaddleOCR plus line
    segmentation.
    """
    engine = engine.lower()
    if engine != "tesseract":
        raise ValueError(f"Unsupported OCR engine: {engine}")
    return _extract_with_tesseract(path)


def _extract_with_tesseract(path: str | Path) -> OcrResult:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "Tesseract OCR dependencies are not installed. Run `pip install -e \".[ocr]\"` "
            "and install the tesseract system binary."
        ) from exc

    image = Image.open(path)
    text = pytesseract.image_to_string(image)
    return OcrResult(text=text.strip(), confidence=None, engine="tesseract", source=str(path))

