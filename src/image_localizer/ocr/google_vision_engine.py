"""Google Cloud Vision OCR engine.

Uses Vision's ``document_text_detection`` (best for dense marketing/product
imagery) and emits one :class:`TextBlock` per detected word. The downstream
line-clustering (``_cluster_lines``) rebuilds logical lines, so word-level
output stays consistent with the other engines while giving tight per-word
boxes for the stroke-level erase.

Authentication (either works):
- ``GOOGLE_APPLICATION_CREDENTIALS`` pointing at a service-account JSON file
  (the standard Application Default Credentials flow), or
- ``GOOGLE_API_KEY`` for a simple API-key client.

Both are read from the environment, so they can live in the project ``.env``.
"""

from __future__ import annotations

import os
from pathlib import Path

from image_localizer.models import TextBlock
from image_localizer.ocr.base import OCREngine

# Minimum per-word confidence and size to keep. Vision is reliable, so these are
# light filters that only drop obvious noise, not faint-but-real text.
_MIN_CONFIDENCE = 0.3
_MIN_WIDTH = 8
_MIN_HEIGHT = 6


class GoogleVisionOCREngine(OCREngine):
    def __init__(self, api_key: str | None = None) -> None:
        try:
            from google.cloud import vision
        except ImportError as exc:
            raise ImportError(
                "google-cloud-vision is required. Install with: "
                "pip install google-cloud-vision"
            ) from exc

        self._vision = vision
        api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            from google.api_core.client_options import ClientOptions

            self.client = vision.ImageAnnotatorClient(
                client_options=ClientOptions(api_key=api_key)
            )
        else:
            # Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
            self.client = vision.ImageAnnotatorClient()

    @property
    def name(self) -> str:
        return "google"

    def extract_text(self, image_path: Path) -> list[TextBlock]:
        content = Path(image_path).read_bytes()
        image = self._vision.Image(content=content)
        response = self.client.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(
                f"Google Vision API error: {response.error.message}"
            )
        blocks = _words_from_annotation(response.full_text_annotation)
        return _sort_blocks(blocks)


def _words_from_annotation(annotation) -> list[TextBlock]:
    """Convert a Vision ``full_text_annotation`` into word-level text blocks.

    Kept as a free function (independent of the API client) so it can be unit
    tested with lightweight fake annotation objects.
    """
    blocks: list[TextBlock] = []
    for page in annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join(symbol.text for symbol in word.symbols).strip()
                    if not text:
                        continue
                    vertices = word.bounding_box.vertices
                    xs = [int(v.x) for v in vertices]
                    ys = [int(v.y) for v in vertices]
                    x, y = min(xs), min(ys)
                    w = max(xs) - x
                    h = max(ys) - y
                    if w < _MIN_WIDTH or h < _MIN_HEIGHT:
                        continue
                    confidence = float(getattr(word, "confidence", 0.0) or 0.0)
                    if confidence and confidence < _MIN_CONFIDENCE:
                        continue
                    blocks.append(
                        TextBlock(
                            text=text,
                            x=x,
                            y=y,
                            width=w,
                            height=h,
                            confidence=confidence,
                        )
                    )
    return blocks


def _sort_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    # Top-to-bottom, then left-to-right.
    return sorted(blocks, key=lambda b: (b.y, b.x))
