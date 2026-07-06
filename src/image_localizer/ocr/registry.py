from __future__ import annotations

from image_localizer.ocr.base import OCREngine
from image_localizer.ocr.easyocr_engine import EasyOCREngine
from image_localizer.ocr.google_vision_engine import GoogleVisionOCREngine
from image_localizer.ocr.tesseract_engine import TesseractEngine


def get_ocr_engine(name: str) -> OCREngine:
    name = name.lower()
    if name == "easyocr":
        return EasyOCREngine()
    if name == "tesseract":
        return TesseractEngine()
    if name in ("google", "google-vision", "vision"):
        return GoogleVisionOCREngine()
    raise ValueError(
        f"Unsupported OCR engine: {name}. Choose from: {', '.join(list_ocr_engines())}"
    )


def list_ocr_engines() -> list[str]:
    return ["easyocr", "tesseract", "google"]
