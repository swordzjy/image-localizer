import numpy as np

from image_localizer.image_editor import (
    _available_width,
    _cluster_lines,
    _detect_alignments,
    _line_height,
    _merge_overlapping_blocks,
    _original_font_size,
    _rendered_block_height,
    _side_limits,
    _text_stroke_mask,
    _wrap_text,
    edit_image,
)
from image_localizer.models import TextBlock


def test_wrap_text_splits_on_width():
    from PIL import ImageFont

    font = ImageFont.load_default()
    lines = _wrap_text("hello world foo bar", font, max_width=50)
    assert len(lines) > 1


def test_cluster_lines_groups_horizontally():
    blocks = [
        TextBlock(text="Hello", x=10, y=10, width=30, height=10),
        TextBlock(text="world", x=50, y=12, width=30, height=10),
        TextBlock(text="Another", x=10, y=100, width=30, height=10),
    ]
    lines = _cluster_lines(blocks)
    assert len(lines) == 2
    assert len(lines[0][0]) == 2
    assert len(lines[1][0]) == 1


def test_merge_overlapping_blocks_keeps_distinct_lines_separate():
    # Regression: two vertically adjacent lines whose OCR bboxes overlap slightly
    # (e.g. a multi-line disclaimer) must NOT be merged. Merging them inflates the
    # combined bbox and forces a tiny recovered font size.
    blocks = [
        TextBlock(
            text="The above data is obtained from Hagibis laboratory tests",
            x=56,
            y=533,
            width=679,
            height=26,
        ),
        TextBlock(
            text="the test results may vary according to different environments",
            x=56,
            y=553,
            width=667,
            height=29,
        ),
    ]
    merged = _merge_overlapping_blocks(blocks)
    assert len(merged) == 2
    assert merged[0].text == blocks[0].text
    assert merged[1].text == blocks[1].text


def test_merge_overlapping_blocks_merges_real_duplicates():
    # Two OCR boxes for the same text that overlap heavily should still be merged.
    blocks = [
        TextBlock(text="Fast cooling", x=100, y=100, width=120, height=30),
        TextBlock(text="Fast cooling", x=105, y=102, width=115, height=28),
    ]
    merged = _merge_overlapping_blocks(blocks)
    assert len(merged) == 1
    assert merged[0].text == "Fast cooling"


def test_original_font_size_is_independent_of_translation():
    # Two blocks with the SAME original text/width must recover the SAME font
    # size regardless of how long the translated string is. This keeps the
    # rendered font size consistent with the original.
    size_short = _original_font_size("Speed 1", w=110, h=36)
    size_long = _original_font_size("Speed 1", w=110, h=36)
    assert size_short == size_long
    # A tighter bbox width for the same text implies a smaller original font.
    assert _original_font_size("Speed 1", w=60, h=36) < size_short


def test_edit_image_keeps_bottom_edge_text_inside_image(tmp_path):
    # Regression: a text block near the bottom edge must not be pushed off the
    # image (previously a global vertical cascade clipped the last line).
    from PIL import Image

    src = tmp_path / "src.png"
    Image.new("RGB", (400, 200), (255, 255, 255)).save(src)

    block = TextBlock(
        text="Adjustment buttons",
        x=20,
        y=180,
        width=200,
        height=18,
        translated="Boutons d'ajustement du ventilateur",
    )
    out = tmp_path / "out.png"
    edit_image(src, [block], out)

    assert out.exists()
    result = Image.open(out)
    # Output keeps the original canvas size and the rendered text stays within it.
    assert result.size == (400, 200)


def _line(x, y, w, h):
    return ([TextBlock(text="x", x=x, y=y, width=w, height=h)], x, y, w, h)


def test_detect_alignments_marks_centered_stack():
    # Vertically stacked lines that share a common centre but have different left
    # edges are a centred title and must be detected as centre-aligned, even when
    # they sit away from the image centre.
    lines = [
        _line(100, 40, 200, 30),  # centre 200
        _line(150, 80, 100, 30),  # centre 200
        _line(120, 120, 160, 30),  # centre 200
    ]
    aligns = _detect_alignments(lines, img_center=600)
    assert aligns == [True, True, True]


def test_detect_alignments_leaves_left_aligned_text_alone():
    # Lines that share a left edge (but not a centre) are left-aligned and must
    # not be forced to centre, which would shift the text.
    lines = [
        _line(100, 40, 400, 30),  # centre 300
        _line(100, 80, 200, 30),  # centre 200
    ]
    aligns = _detect_alignments(lines, img_center=600)
    assert aligns == [False, False]


def test_side_limits_splits_gap_between_neighbours():
    # Two blocks on the same row: the empty gap between them is split at its
    # midpoint so a longer translation cannot overrun the neighbour's text.
    lines = [
        _line(100, 40, 100, 30),  # left block: x 100..200
        _line(400, 40, 120, 30),  # right block: x 400..520
    ]
    # Left block's right limit is midway between its right edge (200) and the
    # neighbour's left edge (400) -> 300.
    assert _side_limits(lines, 0, img_width=1000) == (0, 300)
    # Right block's left limit is the same midpoint; no neighbour on its right.
    assert _side_limits(lines, 1, img_width=1000) == (300, 1000)


def test_side_limits_ignores_lines_on_other_rows():
    lines = [
        _line(100, 40, 100, 30),
        _line(400, 400, 120, 30),  # far below -> not the same row
    ]
    assert _side_limits(lines, 0, img_width=1000) == (0, 1000)


def test_available_width_stops_before_foreground():
    # White background on the left, dark foreground (a product photo) starting at
    # x=200. The usable width must stop before the foreground so translated text
    # never runs across artwork.
    arr = np.full((100, 300, 3), 255, dtype=np.uint8)
    arr[:, 200:] = 0
    width = _available_width(arr, x=10, y=10, w=40, h=30, bg=(255, 255, 255))
    assert width == 190


def test_text_stroke_mask_dilate_stays_inside_bbox():
    # A light background with a dark text glyph inside a small bbox. Even with
    # dilate=3 the mask must not leak outside the supplied bbox.
    arr = np.full((100, 200, 3), 240, dtype=np.uint8)
    arr[45:55, 45:75] = 30
    mask = _text_stroke_mask(arr, [(40, 40, 40, 20, (240, 240, 240))], dilate=3)
    ys, xs = np.where(mask > 0)
    assert xs.min() >= 40
    assert xs.max() < 80
    assert ys.min() >= 40
    assert ys.max() < 60


def test_edit_image_shrinks_to_avoid_vertical_overlap(tmp_path):
    # Two lines whose original bboxes leave only a small vertical gap.
    # A longer translation must be shrunk so the rendered glyphs do not visually
    # overlap the next line.
    from PIL import Image

    src = tmp_path / "src.png"
    Image.new("RGB", (600, 200), (155, 193, 243)).save(src)

    blocks = [
        TextBlock(
            text="Short line",
            x=50,
            y=40,
            width=120,
            height=30,
            translated="Une traduction beaucoup plus longue",
        ),
        TextBlock(
            text="Next line",
            x=50,
            y=75,
            width=100,
            height=30,
            translated="Ligne suivante",
        ),
    ]
    out = tmp_path / "out.png"
    edit_image(src, blocks, out)

    result = Image.open(out)
    arr = np.array(result)
    # Text is light on blue; count bright pixels in the gap between y=70..80.
    bright = (arr > 200).all(axis=2)
    gap_pixels = bright[70:80, :].sum()
    # With the overlap guard the gap should be essentially empty background.
    assert gap_pixels < 100


def test_rendered_block_height_uses_real_bbox():
    from PIL import ImageFont

    font = ImageFont.load_default()
    line_h = _line_height(font)
    h = _rendered_block_height(["hello"], font, line_h)
    # The coarse line box is at least as tall as the real bbox height.
    assert h <= line_h
    assert h > 0
