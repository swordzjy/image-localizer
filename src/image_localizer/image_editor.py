from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from image_localizer.models import TextBlock


def _has_cjk(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3040 <= code <= 0x309F
            or 0x30A0 <= code <= 0x30FF
            or 0xAC00 <= code <= 0xD7AF
        ):
            return True
    return False


def _get_font(size: int, text: str = "", bold: bool = False) -> ImageFont.FreeTypeFont:
    latin_candidates = []
    cjk_candidates = []
    if bold:
        latin_candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        cjk_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/PingFang.ttc",
        ]
    else:
        latin_candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/NotoSans.ttf",
        ]
        cjk_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]

    candidates = cjk_candidates if _has_cjk(text) else latin_candidates
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Fallback: try any candidate
    for path in latin_candidates + cjk_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_size(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if _has_cjk(text) or " " not in text:
        return _wrap_by_char(text, font, max_width)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        # If a single word is already too wide, break it character by character.
        if _text_size(word, font)[0] > max_width:
            if current:
                lines.append(current)
                current = ""
            for ch in word:
                test = current + ch
                if _text_size(test, font)[0] <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = ch
            continue

        test = f"{current} {word}" if current else word
        w, _ = _text_size(test, font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrap_by_char(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        w, _ = _text_size(test, font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def _contrast_color(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    luminance = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (34, 34, 34) if luminance > 128 else (255, 255, 255)


def _sample_bg(
    arr: np.ndarray, x: int, y: int, w: int, h: int, pad: int = 8
) -> tuple[int, int, int]:
    """Sample the background behind a text block.

    We compare a thin band just inside the OCR bbox (the label/speech-bubble
    colour) with a ring just outside the bbox (the page background). If the
    inner band is uniform and very different from the outer ring, the text is
    sitting on a solid label and we should use the inner colour to erase the
    original text. Otherwise we use the outer colour.
    """
    ih, iw = arr.shape[:2]

    # Outer ring around the bbox
    ox1 = max(0, x - pad)
    oy1 = max(0, y - pad)
    ox2 = min(iw, x + w + pad)
    oy2 = min(ih, y + h + pad)

    # Inner band just inside the bbox
    inner_margin = 3
    ix1 = min(x + inner_margin, ox2)
    iy1 = min(y + inner_margin, oy2)
    ix2 = max(x + w - inner_margin, ox1)
    iy2 = max(y + h - inner_margin, oy1)

    outer_coords: list[tuple[int, int]] = []
    for px in range(ox1, ox2):
        outer_coords.append((px, oy1))
        if oy2 - 1 != oy1:
            outer_coords.append((px, oy2 - 1))
    for py in range(oy1 + 1, oy2 - 1):
        outer_coords.append((ox1, py))
        if ox2 - 1 != ox1:
            outer_coords.append((ox2 - 1, py))

    # Exclude the original bbox from the outer ring
    outer_coords = [
        (px, py)
        for px, py in outer_coords
        if not (x <= px < x + w and y <= py < y + h)
    ]

    inner_coords: list[tuple[int, int]] = []
    if ix2 > ix1 and iy2 > iy1:
        for px in range(ix1, ix2):
            inner_coords.append((px, iy1))
            if iy2 - 1 != iy1:
                inner_coords.append((px, iy2 - 1))
        for py in range(iy1 + 1, iy2 - 1):
            inner_coords.append((ix1, py))
            if ix2 - 1 != ix1:
                inner_coords.append((ix2 - 1, py))

    if not outer_coords and not inner_coords:
        return (240, 240, 240)

    outer_pixels = np.array([arr[py, px] for px, py in outer_coords]) if outer_coords else np.array([])
    inner_pixels = np.array([arr[py, px] for px, py in inner_coords]) if inner_coords else np.array([])

    def _median(pixels: np.ndarray) -> tuple[int, int, int]:
        color = np.median(pixels, axis=0).astype(int)
        return (int(color[0]), int(color[1]), int(color[2]))

    outer_color = _median(outer_pixels) if outer_pixels.size else (240, 240, 240)

    if inner_pixels.size < 8:
        return outer_color

    inner_color = _median(inner_pixels)
    inner_std = float(np.std(inner_pixels.astype(float), axis=0).mean())
    contrast = _color_distance(inner_color, outer_color)

    # If the inside of the bbox is a uniform, strongly contrasting label,
    # use that label colour to paint over the original text.
    if inner_std < 25 and contrast > 40:
        return inner_color
    return outer_color


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(np.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))


def _estimate_text_color(
    arr: np.ndarray, x: int, y: int, w: int, h: int, bg: tuple[int, int, int]
) -> tuple[int, int, int]:
    ih, iw = arr.shape[:2]
    x1 = max(0, x + 2)
    y1 = max(0, y + 2)
    x2 = min(iw, x + w - 2)
    y2 = min(ih, y + h - 2)
    if x2 <= x1 or y2 <= y1:
        return _contrast_color(bg)

    region = arr[y1:y2, x1:x2].reshape(-1, 3)
    bg_arr = np.array(bg)
    distances = np.linalg.norm(region.astype(float) - bg_arr, axis=1)
    mask = distances > 30
    if mask.sum() == 0:
        return _contrast_color(bg)

    text_pixels = region[mask]
    text_distances = distances[mask]
    # Target solid stroke cores rather than anti-aliased edges. The median of
    # all text pixels is often dominated by grey fringe pixels, which makes
    # small/thin translated text look washed-out. Using the half of pixels that
    # are farthest from the background recovers the original ink colour while
    # still tolerating anti-aliasing.
    threshold = np.percentile(text_distances, 50)
    stroke_pixels = text_pixels[text_distances >= threshold]
    color = np.median(stroke_pixels, axis=0).astype(int)
    color_t = (int(color[0]), int(color[1]), int(color[2]))
    # Guard against near-invisible text: when the recovered colour barely
    # differs from the background, fall back to a high-contrast colour so the
    # translated text stays legible instead of rendering blurry or blank.
    if _color_distance(color_t, bg) < 55:
        return _contrast_color(bg)
    return color_t


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / min(area_a, area_b)


def _merge_overlapping_blocks(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    """Merge duplicate/overlapping OCR boxes to avoid repeated text."""
    if not blocks:
        return []

    sorted_blocks = sorted(blocks, key=lambda b: (b.y, b.x))
    merged: list[TextBlock] = []
    for block in sorted_blocks:
        bbox = block.bbox
        absorbed = False
        for i, m in enumerate(merged):
            iou = _iou(bbox, m.bbox)
            contained = iou >= 0.85
            overlaps = iou >= 0.5
            if contained or overlaps:
                x1 = min(m.x, block.x)
                y1 = min(m.y, block.y)
                x2 = max(m.x + m.width, block.x + block.width)
                y2 = max(m.y + m.height, block.y + block.height)
                new_text = m.text
                if block.text.lower() != m.text.lower() and block.text not in m.text:
                    new_text = f"{m.text} {block.text}"
                merged[i] = TextBlock(
                    text=new_text,
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    confidence=max(m.confidence, block.confidence),
                    translated=m.translated,
                )
                absorbed = True
                break
        if not absorbed:
            merged.append(block)
    return merged


def _to_hex(color: tuple[int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _cluster_lines(blocks: Sequence[TextBlock]) -> list[tuple[list[TextBlock], int, int, int, int]]:
    """Group blocks into horizontal lines and return (blocks, x, y, w, h)."""
    sorted_blocks = sorted(blocks, key=lambda b: (b.y, b.x))
    lines: list[list[TextBlock]] = []
    for block in sorted_blocks:
        cy = block.y + block.height / 2
        placed = False
        for line in lines:
            line_y = line[0].y
            line_h = line[0].height
            # Keep the threshold tight so adjacent labels/bubbles are not merged.
            threshold = min(block.height, line_h) * 0.45 + 3
            if abs(cy - (line_y + line_h / 2)) < threshold:
                line.append(block)
                placed = True
                break
        if not placed:
            lines.append([block])

    result = []
    for line in lines:
        line.sort(key=lambda b: b.x)
        # Split a line into sub-lines if blocks are far apart horizontally,
        # so a single translated line does not span unrelated labels/bubbles.
        sub_lines: list[list[TextBlock]] = []
        current: list[TextBlock] = []
        for b in line:
            if not current:
                current.append(b)
                continue
            prev = current[-1]
            gap = b.x - (prev.x + prev.width)
            threshold = max(20, (prev.height + b.height) / 2 * 0.8)
            if gap > threshold:
                sub_lines.append(current)
                current = [b]
            else:
                current.append(b)
        sub_lines.append(current)

        for sub in sub_lines:
            x = min(b.x for b in sub)
            y = min(b.y for b in sub)
            right = max(b.x + b.width for b in sub)
            bottom = max(b.y + b.height for b in sub)
            result.append((sub, x, y, right - x, bottom - y))
    return result


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    """Full single-line advance (ascent + descent) so lines never clip or overlap."""
    ascent, descent = font.getmetrics()
    return ascent + descent


def _size_for_height(target_h: int, text: str = "") -> int:
    """Return the font size whose rendered glyph height matches the original bbox
    height ``target_h``.

    The size is derived only from the original text height, independently of the
    (usually longer) translated string, so a given original font size always maps
    to the same rendered size. Fitting the translated text to the available width
    is handled separately by wrapping, not by shrinking the font.
    """
    sample = text if _has_cjk(text) else "Ayg"
    if not sample:
        sample = "Ayg"
    size = max(6, int(round(target_h)) + 6)
    while size > 6:
        try:
            glyph_h = _text_size(sample, _get_font(size, sample))[1]
        except OSError:
            size -= 1
            continue
        if glyph_h <= target_h:
            return size
        size -= 1
    return 6


def _original_font_size(original_text: str, w: int, h: int) -> int:
    """Recover the font size the source used, from the tight OCR bbox *width*.

    The bounding-box width bounds the original text at its true size far more
    tightly than the (often loose) bounding-box height, so it recovers the
    original point size reliably. The translated text is then rendered at this
    same size, keeping the rendered font size consistent with the original.
    Falls back to a height-based estimate when there is no original text to
    measure.
    """
    text = original_text.strip()
    if not text:
        return _size_for_height(h)
    best = 8
    upper = min(300, max(12, h * 4))
    for size in range(8, upper):
        try:
            width = _text_size(text, _get_font(size, text))[0]
        except OSError:
            continue
        if width <= w:
            best = size
    return best


def _text_stroke_mask(
    arr: np.ndarray,
    regions: Sequence[tuple[int, int, int, int, tuple[int, int, int]]],
    dist_threshold: int = 38,
    dilate: int = 1,
) -> np.ndarray:
    """Build a mask covering only the original *text strokes*.

    For each region we mark the pixels that differ from the local background
    colour (i.e. the glyphs) and optionally dilate them to catch anti-aliased
    edges. Inpainting this mask removes the original text while leaving the
    surrounding gradient/texture/photo intact, instead of painting a flat
    rectangle over it.

    The reference background colour is taken from the *median* of a thin ring
    just outside each bbox. This handles lines that cross multiple background
    regions (e.g. a light backdrop next to a dark product in A+_06) far better
    than a single global background sample: the ring is local to the text edge,
    so it does not misclassify a neighbouring background region as a stroke.

    The distance threshold is also adaptive: the same outer ring is used to
    measure how much the local background naturally varies. Only pixels that
    exceed the high percentile of that background variation are treated as text
    strokes. This prevents textured backgrounds from being smoothed away by
    inpainting.
    """
    ih, iw = arr.shape[:2]
    mask = np.zeros((ih, iw), dtype=np.uint8)
    arr_f = arr.astype(np.float32)
    for x, y, w, h, _bg in regions:
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(iw, x + w), min(ih, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        # Sample a thin ring just outside the bbox for both the local
        # background colour and the natural background variation.
        ox1 = max(0, x - 2)
        oy1 = max(0, y - 2)
        ox2 = min(iw, x + w + 2)
        oy2 = min(ih, y + h + 2)
        outer_parts: list[np.ndarray] = []
        if x1 > ox1:
            outer_parts.append(arr_f[oy1:oy2, ox1:x1].reshape(-1, 3))
        if ox2 > x2:
            outer_parts.append(arr_f[oy1:oy2, x2:ox2].reshape(-1, 3))
        if y1 > oy1:
            outer_parts.append(arr_f[oy1:y1, x1:x2].reshape(-1, 3))
        if oy2 > y2:
            outer_parts.append(arr_f[y2:oy2, x1:x2].reshape(-1, 3))

        if not outer_parts:
            continue

        outer_pixels = np.concatenate(outer_parts, axis=0)
        if outer_pixels.shape[0] < 4:
            continue

        local_bg = np.median(outer_pixels, axis=0).astype(np.float32)
        outer_dist = np.sqrt(((outer_pixels - local_bg) ** 2).sum(axis=1))
        adaptive_threshold = max(
            float(dist_threshold), float(np.percentile(outer_dist, 92))
        )

        region = arr_f[y1:y2, x1:x2]
        dist = np.sqrt(((region - local_bg) ** 2).sum(axis=2))
        stroke = (dist > adaptive_threshold).astype(np.uint8) * 255

        # Dilate inside the region's own bbox so the mask can cover faint
        # shadows/duplicate text behind the glyphs without spilling onto
        # neighbouring product artwork outside the bbox.
        if dilate > 0:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1)
            )
            stroke = cv2.dilate(stroke, kernel)

        mask[y1:y2, x1:x2] = np.maximum(mask[y1:y2, x1:x2], stroke)
    return mask


# When a translation is much longer than the source, the original font size is
# scaled down to fit the clear area — but never below these limits, so the text
# stays legible and instead wraps once the floor is reached.
_MIN_FONT_SCALE = 0.6
_MIN_FONT_SIZE = 10


def _bg_span(
    arr: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    bg: tuple[int, int, int],
    dist_threshold: int = 60,
    bg_fraction: float = 0.6,
) -> tuple[int, int]:
    """Return the ``(left, right)`` columns bounding the background around a region.

    Scans left from the region's left edge and right from its right edge while
    each column stays mostly background (close to ``bg``), stopping at the first
    column that hits foreground content — a product photo, a neighbouring block,
    or the image edge. Used to bound how far translated text may extend on each
    side without running across artwork.
    """
    ih, iw = arr.shape[:2]
    y1, y2 = max(0, y), min(ih, y + h)
    bg_f = np.array(bg, dtype=np.float32)

    def is_bg(col: int) -> bool:
        strip = arr[y1:y2, col].astype(np.float32)
        dist = np.sqrt(((strip - bg_f) ** 2).sum(axis=1))
        return float(np.mean(dist <= dist_threshold)) >= bg_fraction

    if y2 <= y1:
        return max(0, x), min(iw, x + w)

    right = min(iw, x + w)
    while right < iw and is_bg(right):
        right += 1
    left = max(0, x)
    while left > 0 and is_bg(left - 1):
        left -= 1
    return left, right


def _available_width(
    arr: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    bg: tuple[int, int, int],
    dist_threshold: int = 60,
    bg_fraction: float = 0.6,
) -> int:
    """Measure how far the background extends to the right of a text region.

    Scans columns rightward from the region's right edge while each column is
    still mostly background (close to ``bg``). Returns the total usable width,
    from ``x`` to the first column that hits foreground content — a product
    photo, a neighbouring text block, or the image edge. This keeps a longer
    translation from running across artwork (e.g. onto a dark product where the
    text becomes invisible) instead of wrapping within the space the original
    designer left clear.
    """
    ih, iw = arr.shape[:2]
    y1, y2 = max(0, y), min(ih, y + h)
    if y2 <= y1:
        return max(1, w)
    bg_f = np.array(bg, dtype=np.float32)
    col = min(iw, x + w)
    while col < iw:
        strip = arr[y1:y2, col].astype(np.float32)
        dist = np.sqrt(((strip - bg_f) ** 2).sum(axis=1))
        if float(np.mean(dist <= dist_threshold)) < bg_fraction:
            break
        col += 1
    return max(w, col - x)


def _detect_alignments(
    lines: Sequence[tuple[Sequence[TextBlock], int, int, int, int]],
    img_center: float,
) -> list[bool]:
    """Classify each clustered line as centre-aligned (``True``) or left-aligned.

    Two signals are combined:
    - A line whose horizontal centre sits close to the image centre is treated
      as centre-aligned (typical for banner titles).
    - Vertically stacked lines that share a common centre but have differing
      left edges are centre-aligned as a group (multi-line centred titles).

    Centre-aligned source text must stay centred; otherwise translated titles
    that were centred in the original drift left and look broken.
    """
    n = len(lines)
    result = [False] * n
    tol = max(8.0, img_center * 0.06)

    # Signal 1: the line's centre is near the image centre.
    for i, (_lb, x, _y, w, _h) in enumerate(lines):
        if abs((x + w / 2) - img_center) <= tol:
            result[i] = True

    # Signal 2: a vertical stack of lines sharing a centre (but not a left edge).
    def flush(group: list[int]) -> None:
        if len(group) < 2:
            return
        centers = [lines[i][1] + lines[i][3] / 2 for i in group]
        lefts = [lines[i][1] for i in group]
        center_spread = max(centers) - min(centers)
        left_spread = max(lefts) - min(lefts)
        if left_spread > 4 and center_spread <= left_spread:
            for i in group:
                result[i] = True

    order = sorted(range(n), key=lambda i: lines[i][2])
    stack: list[int] = []
    for idx in order:
        _lb, x, y, w, h = lines[idx]
        if stack:
            _lb2, x2, y2, w2, h2 = lines[stack[-1]]
            overlap = min(x + w, x2 + w2) - max(x, x2)
            gap = y - (y2 + h2)
            if overlap > 0 and gap <= max(h, h2) * 1.6:
                stack.append(idx)
                continue
            flush(stack)
        stack = [idx]
    flush(stack)
    return result


def _side_limits(
    lines: Sequence[tuple[Sequence[TextBlock], int, int, int, int]],
    index: int,
    img_width: int,
) -> tuple[int, int]:
    """Bound a line horizontally by the neighbouring lines sharing its row.

    Card/panel boundaries are often the same light colour as the gap between
    them and cannot be found by colour alone. But the neighbouring *text* blocks
    are known, so the empty gap between two adjacent blocks on the same row is
    split at its midpoint: a translation that grows longer than its source may
    expand into at most half the gap and cannot overrun a neighbour's text.
    """
    _lb, xi, yi, wi, hi = lines[index]
    left_limit = 0
    right_limit = img_width
    for j, (_lb2, xj, yj, wj, hj) in enumerate(lines):
        if j == index:
            continue
        if min(yi + hi, yj + hj) - max(yi, yj) <= 0:
            continue  # no vertical overlap → not on the same row
        if xj + wj <= xi:  # neighbour entirely to the left
            left_limit = max(left_limit, (xj + wj + xi) // 2)
        elif xj >= xi + wi:  # neighbour entirely to the right
            right_limit = min(right_limit, (xi + wi + xj) // 2)
    return left_limit, right_limit


def edit_image(image_path: Path, blocks: Sequence[TextBlock], output_path: Path, use_inpaint: bool = False) -> None:
    if not blocks:
        # Nothing to edit; just copy
        Image.open(image_path).save(output_path)
        return

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)
    blocks = _merge_overlapping_blocks(blocks)
    lines = _cluster_lines(blocks)
    aligns = _detect_alignments(lines, img.width / 2)

    # Build a render plan and, in parallel, the regions whose original text must
    # be erased. Erasing happens at the *stroke* level (see below), so the
    # surrounding background — gradients, textures, product photos — is kept
    # intact instead of being covered by a flat rectangle.
    plan: list[dict] = []
    erase_regions: list[tuple[int, int, int, int, tuple[int, int, int]]] = []
    for i, (line_blocks, x, y, w, h) in enumerate(lines):
        original_text = " ".join(b.text for b in line_blocks)
        translated = line_blocks[0].translated or original_text
        if not translated.strip():
            continue

        bg = _sample_bg(arr, x, y, w, h)
        text_color = _estimate_text_color(arr, x, y, w, h, bg)

        # Reproduce the original font size (recovered from the tight bbox width),
        # then render the translated text at that same size. Allow the text to
        # extend toward the right edge and only wrap when it is genuinely too
        # long, rather than shrinking the font to fit the original width. This
        # keeps the rendered font size consistent with the original.
        size = _original_font_size(original_text, w, h)
        font = _get_font(size, translated)
        hex_color = _to_hex(text_color)

        # Only wrap the translation within the space the original design left
        # clear: bound the width by the background span on each side so the text
        # never runs across a product photo (where it would become invisible).
        # For centred titles keep the budget symmetric around the centre.
        is_center = aligns[i]
        center = x + w / 2
        left_bg, right_bg = _bg_span(arr, x, y, w, h, bg)
        left_lim, right_lim = _side_limits(lines, i, img.width)
        left_bound = max(left_bg, left_lim)
        right_bound = min(right_bg, right_lim)
        if is_center:
            reach = min(center - left_bound, right_bound - center)
            max_text_width = max(w, int(2 * reach) - 8)
        else:
            max_text_width = max(w, right_bound - x)

        # Keep the original font size when the translation is a similar length,
        # but shrink it (down to a floor) when the translation is much longer
        # than the source — otherwise the same size would overflow the clear
        # area, run onto artwork, or get clipped. Below the floor it wraps.
        single_w = _text_size(translated, font)[0]
        if single_w > max_text_width and single_w > 0:
            scale = max(_MIN_FONT_SCALE, max_text_width / single_w)
            shrunk = max(_MIN_FONT_SIZE, int(size * scale))
            if shrunk < size:
                size = shrunk
                font = _get_font(size, translated)

        lines_text = _wrap_text(translated, font, max_text_width)
        if not lines_text:
            continue

        line_h = _line_height(font)
        total_h = len(lines_text) * line_h

        # Anchor each line at its ORIGINAL position (top-aligned like the source
        # text). Do not push lines around relative to other lines, which used to
        # make text drift down the page and run off the bottom edge. Only clamp so
        # a block near the bottom edge stays fully inside the image.
        render_y = y
        if render_y + total_h > img.height:
            render_y = max(0, img.height - total_h)

        # Erase only the original text's own bounding box (its strokes), not the
        # wider translated text, so we never paint over neighbouring artwork.
        erase_regions.append((x, y, w, h, bg))

        plan.append(
            {
                "text_color": hex_color,
                "font": font,
                "lines": lines_text,
                "line_h": line_h,
                "render_y": render_y,
                "x": x,
                "align": "center" if is_center else "left",
                "center": center,
            }
        )

    # Remove the original text by inpainting only its strokes, which preserves
    # the underlying background (gradient/texture/photo) around the glyphs.
    mask = _text_stroke_mask(arr, erase_regions)
    if mask.any():
        arr = cv2.inpaint(np.ascontiguousarray(arr), mask, 3, cv2.INPAINT_TELEA)
    img = Image.fromarray(arr)

    draw = ImageDraw.Draw(img)
    for p in plan:
        cur_y = p["render_y"]
        for line in p["lines"]:
            if p["align"] == "center":
                line_w = _text_size(line, p["font"])[0]
                lx = int(round(p["center"] - line_w / 2))
                lx = max(0, min(lx, img.width - line_w))
            else:
                lx = p["x"]
            draw.text((lx, cur_y), line, font=p["font"], fill=p["text_color"])
            cur_y += p["line_h"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
