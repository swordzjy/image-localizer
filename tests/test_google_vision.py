from types import SimpleNamespace

from image_localizer.ocr.google_vision_engine import _words_from_annotation


def _word(text, x, y, w, h, confidence=0.9):
    symbols = [SimpleNamespace(text=ch) for ch in text]
    vertices = [
        SimpleNamespace(x=x, y=y),
        SimpleNamespace(x=x + w, y=y),
        SimpleNamespace(x=x + w, y=y + h),
        SimpleNamespace(x=x, y=y + h),
    ]
    return SimpleNamespace(
        symbols=symbols,
        bounding_box=SimpleNamespace(vertices=vertices),
        confidence=confidence,
    )


def _annotation(words):
    paragraph = SimpleNamespace(words=words)
    block = SimpleNamespace(paragraphs=[paragraph])
    page = SimpleNamespace(blocks=[block])
    return SimpleNamespace(pages=[page])


def test_words_from_annotation_maps_words_to_text_blocks():
    annotation = _annotation([
        _word("Cooling", 100, 50, 120, 30),
        _word("fast", 230, 50, 60, 30),
    ])

    blocks = _words_from_annotation(annotation)

    assert [b.text for b in blocks] == ["Cooling", "fast"]
    first = blocks[0]
    assert (first.x, first.y, first.width, first.height) == (100, 50, 120, 30)
    assert first.confidence == 0.9


def test_words_from_annotation_drops_tiny_and_empty_words():
    annotation = _annotation([
        _word("ok", 10, 10, 40, 20),
        _word("x", 10, 10, 4, 4),      # too small -> dropped
        _word("   ", 10, 10, 40, 20),  # empty after strip -> dropped
    ])

    blocks = _words_from_annotation(annotation)

    assert [b.text for b in blocks] == ["ok"]


def test_words_from_annotation_drops_low_confidence():
    annotation = _annotation([
        _word("keep", 10, 10, 50, 20, confidence=0.8),
        _word("noise", 10, 40, 50, 20, confidence=0.1),
    ])

    blocks = _words_from_annotation(annotation)

    assert [b.text for b in blocks] == ["keep"]
