from __future__ import annotations

from pathlib import Path

from image_localizer.models import TextBlock
from image_localizer.ocr.base import OCREngine


class EasyOCREngine(OCREngine):
    def __init__(self, languages: list[str] | None = None, gpu: bool = False) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise ImportError("easyocr is required. Install with: pip install easyocr") from exc
        self.languages = languages or ["en"]
        self.reader = easyocr.Reader(self.languages, gpu=gpu)

    @property
    def name(self) -> str:
        return "easyocr"

    def extract_text(self, image_path: Path) -> list[TextBlock]:
        # Tuned for product/marketing imagery, where faint, low-contrast, small
        # text (disclaimers, sub-captions) is common and is missed by the
        # defaults — leaving the original text baked into the edited image:
        #   - low_text / text_threshold: pick up fainter text regions
        #   - mag_ratio: upscale so small text is legible to the recogniser
        #   - contrast_ths / adjust_contrast: re-read low-contrast boxes with
        #     enhanced contrast instead of discarding them
        # This also yields cleaner, less fragmented boxes, which avoids the same
        # sentence being split across boxes and re-translated multiple times.
        results = self.reader.readtext(
            str(image_path),
            low_text=0.3,
            text_threshold=0.6,
            mag_ratio=1.6,
            contrast_ths=0.05,
            adjust_contrast=0.7,
        )
        blocks: list[TextBlock] = []
        for bbox, text, conf in results:
            text = text.strip()
            if not text:
                continue
            # Drop low-confidence noise and tiny single-character artifacts. The
            # threshold is deliberately lenient (0.4) because faint marketing
            # text is legitimate but scores lower than body copy; the size
            # filters below remove the small spurious detections this admits.
            if conf < 0.4:
                continue
            xs = [int(p[0]) for p in bbox]
            ys = [int(p[1]) for p in bbox]
            x, y = min(xs), min(ys)
            w = max(xs) - x
            h = max(ys) - y
            if w < 30 or h < 12:
                continue
            blocks.append(TextBlock(text=text, x=x, y=y, width=w, height=h, confidence=float(conf)))
        return _sort_blocks(blocks)


def _sort_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    # Top-to-bottom, then left-to-right
    return sorted(blocks, key=lambda b: (b.y, b.x))
