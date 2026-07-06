from __future__ import annotations

from pathlib import Path

from PIL import Image

from image_localizer.models import TextBlock
from image_localizer.ocr.base import OCREngine


class TesseractEngine(OCREngine):
    def __init__(self, lang: str = "eng") -> None:
        try:
            import pytesseract
        except ImportError as exc:
            raise ImportError("pytesseract is required. Install with: pip install pytesseract") from exc
        self._pytesseract = pytesseract
        self.lang = lang

    @property
    def name(self) -> str:
        return "tesseract"

    def extract_text(self, image_path: Path) -> list[TextBlock]:
        with Image.open(image_path) as img:
            data = self._pytesseract.image_to_data(img, lang=self.lang, output_type=self._pytesseract.Output.DICT)
        blocks: list[TextBlock] = []
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if not text or conf < 30:
                continue
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            blocks.append(TextBlock(text=text, x=x, y=y, width=w, height=h, confidence=conf / 100.0))
        return _sort_blocks(blocks)


def _sort_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    return sorted(blocks, key=lambda b: (b.y, b.x))
