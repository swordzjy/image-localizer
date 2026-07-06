# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`image-localizer` is a Python CLI tool that localizes product images: scrape a product page (or use a local image directory), run OCR, translate the extracted text with an LLM, and render the translated text back onto the images while preserving the original font size, color, and layout.

## Common commands

### Setup

```bash
cd /Users/jianyu/Workspace/image-localizer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Optional extras:

```bash
pip install google-cloud-vision   # for --ocr google
pip install playwright && playwright install chromium  # for --scraper playwright
```

### Run the pipeline

From a local image directory:

```bash
image-localizer localize fr --image-dir ./MC100S --output ./out
```

From a URL:

```bash
image-localizer localize fr --url "https://www.amazon.com/dp/B0CMT5SNFQ" --output ./out --scraper amazon
```

List available plugins:

```bash
image-localizer list-plugins
```

### Tests

```bash
pytest
pytest tests/test_image_editor.py -v
pytest tests/test_image_editor.py::test_name -v
pytest --cov=src --cov-report=term-missing
```

### Linting and formatting

```bash
black src tests
isort src tests
ruff check src tests
```

## Environment variables

The CLI automatically loads `.env` from the project root (or any parent directory) on startup. Existing environment variables take precedence.

Required for LLM translation (at least one):

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

Optional:

- `ANTHROPIC_MODEL` — e.g. `claude-sonnet-5`
- `GOOGLE_APPLICATION_CREDENTIALS` — path to service-account JSON for Google Cloud Vision
- `GOOGLE_API_KEY` — alternative credential for Google Cloud Vision

## High-level architecture

### Entry point and pipeline

- `src/image_localizer/cli.py` defines the `image-localizer` Typer CLI. The `localize` command validates arguments, resolves plugins via registries, and calls `run_pipeline()`.
- `src/image_localizer/pipeline.py` implements the core flow:
  1. **Scrape/download** (when `--url` is given): `scrapers/` → `download.py`
  2. **Collect local images** (when `--image-dir` is given)
  3. **OCR**: `ocr/` engines return a list of `TextBlock`
  4. **Translate**: logical lines are collected, deduplicated, and sent to a `translation/` engine; translations are written back into each `TextBlock.translated`
  5. **Edit**: `image_editor.edit_image()` renders translated text onto each image
  6. **Write outputs**: `manifest.json` and `texts.txt`

### Plugin system

Three interchangeable plugin families are registered in `registry.py` modules:

- **Scrapers**: `src/image_localizer/scrapers/registry.py` — `amazon`, `generic`, `playwright`
- **OCR engines**: `src/image_localizer/ocr/registry.py` — `easyocr` (default), `tesseract`, `google`
- **Translators**: `src/image_localizer/translation/registry.py` — `claude` (default), `openai`

Each family has an abstract base class in `base.py`. Adding a new engine means subclassing the base and registering it in the corresponding registry.

### Core data model (`src/image_localizer/models.py`)

- `ImageAsset` — represents one image, either scraped from a URL or collected from disk.
- `TextBlock` — a detected text region with `x`, `y`, `width`, `height`, `text`, and optional `translated`.

### Image editing (`src/image_localizer/image_editor.py`)

This is the most involved module. It does not just paste text over bounding boxes; it tries to reconstruct the original typography:

1. **Merge overlapping OCR boxes** (`_merge_overlapping_blocks`) so duplicate detections do not create duplicate translations.
2. **Cluster boxes into logical lines** (`_cluster_lines`) and split lines that are far apart horizontally.
3. **Detect center alignment** (`_detect_alignments`) so centered titles stay centered after translation.
4. **Sample background and text colors** (`_sample_bg`, `_estimate_text_color`) from the region around each line.
5. **Recover the original font size** (`_original_font_size`) from the tight OCR bounding-box *width* rather than height, because width correlates more reliably with point size.
6. **Find usable horizontal space** (`_bg_span`, `_side_limits`) so translated text wraps within the clear area instead of running over product photos or neighboring text.
7. **Erase only the original strokes** (`_text_stroke_mask` + OpenCV inpainting) to preserve gradients, textures, and photos behind the text.
8. **Render** the wrapped translation at the recovered size, anchored at the original top-left position and clamped inside the image.

CJK text uses per-character wrapping and prefers CJK system fonts (`_get_font`, `_wrap_by_char`).

### Output layout

```
out/
└── <target_lang>/
    ├── originals/      # original images (downloaded or copied)
    ├── edited/         # images with translated text rendered
    ├── manifest.json   # structured metadata: URLs, text blocks, translations, bbox coordinates
    └── texts.txt       # bilingual side-by-side export: [src] original / [<lang>] translation
```

### Environment loading (`src/image_localizer/env.py`)

A minimal dependency-free `.env` loader. `cli.py` calls `load_dotenv()` before any command. It searches upward from the current working directory for `.env` and never overwrites variables that are already set in the process environment.

## Important constraints and assumptions

- OCR quality determines how much source text remains in the final image. EasyOCR is the default and is tuned for small, low-contrast marketing text. Google Cloud Vision (`--ocr google`) is available for harder cases but is a paid cloud API.
- The editor assumes horizontal, left-to-right text. Arched, vertical, or heavily artistic text will not be reconstructed accurately.
- Font fallback is system-dependent: macOS system fonts are tried first, then common Linux font paths.
- The CLI must be run from inside the virtual environment after `pip install -e .`.
