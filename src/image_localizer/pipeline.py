from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from image_localizer.download import download_images, fetch_page
from image_localizer.image_editor import edit_image
from image_localizer.models import ImageAsset, TextBlock
from image_localizer.ocr.base import OCREngine
from image_localizer.scrapers.base import SiteScraper
from image_localizer.translation.base import Translator


async def _fetch_html(url: str, scraper: SiteScraper) -> str:
    headers = scraper.site_config.get("headers", {})
    async with aiohttp.ClientSession() as session:
        return await fetch_page(session, url, headers=headers)


def _detect_scraper_name(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    if "amazon" in host:
        return "amazon"
    return "generic"


def _collect_local_images(image_dir: Path) -> list[tuple[ImageAsset, Path]]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    paths = sorted(
        p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in exts
    )
    downloaded: list[tuple[ImageAsset, Path]] = []
    for idx, path in enumerate(paths):
        asset = ImageAsset(
            url=path.resolve().as_uri(),
            alt=path.name,
            position=idx,
        )
        downloaded.append((asset, path))
    return downloaded


def _collect_texts(results: list[tuple[ImageAsset, Path, list[TextBlock]]]) -> list[str]:
    seen: set[str] = set()
    texts: list[str] = []
    for _, _, blocks in results:
        # Cluster into lines to get logical translation units
        from image_localizer.image_editor import _cluster_lines

        for line_blocks, _, _, _, _ in _cluster_lines(blocks):
            line_text = " ".join(b.text for b in line_blocks)
            if line_text and line_text not in seen:
                seen.add(line_text)
                texts.append(line_text)
    return texts


def _apply_translations(
    results: list[tuple[ImageAsset, Path, list[TextBlock]]],
    translation_map: dict[str, str],
) -> None:
    from image_localizer.image_editor import _cluster_lines

    for _, _, blocks in results:
        for line_blocks, _, _, _, _ in _cluster_lines(blocks):
            line_text = " ".join(b.text for b in line_blocks)
            translated = translation_map.get(line_text, line_text)
            for b in line_blocks:
                b.translated = translated


def _write_manifest(
    output_dir: Path,
    url: str | None,
    image_dir: Path | None,
    target_lang: str,
    results: list[tuple[ImageAsset, Path, list[TextBlock]]],
) -> None:
    manifest: dict[str, Any] = {
        "source_url": url if url else None,
        "source_image_dir": str(image_dir) if image_dir else None,
        "target_language": target_lang,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "images": [],
    }
    for asset, original_path, blocks in results:
        manifest["images"].append(
            {
                "url": asset.url,
                "original": str(original_path.relative_to(output_dir)),
                "edited": str((output_dir / "edited" / original_path.name).relative_to(output_dir)),
                "text_blocks": [
                    {
                        "text": b.text,
                        "translated": b.translated,
                        "bbox": {
                            "x": b.x,
                            "y": b.y,
                            "width": b.width,
                            "height": b.height,
                        },
                    }
                    for b in blocks
                ],
            }
        )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_texts(
    output_dir: Path,
    target_lang: str,
    results: list[tuple[ImageAsset, Path, list[TextBlock]]],
) -> None:
    """Write a human-readable bilingual text file next to the manifest.

    For every image, each logical line (as clustered for translation) is emitted
    as a ``source`` / ``target`` pair, so the extracted source text and its
    translation can be reviewed side by side without opening the JSON manifest.
    """
    from image_localizer.image_editor import _cluster_lines

    lines_out: list[str] = [
        "# image-localizer bilingual text export",
        f"# target_language: {target_lang}",
        f"# created_at: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for _asset, original_path, blocks in results:
        lines_out.append(f"## {original_path.name}")
        lines_out.append("")
        for line_blocks, _x, _y, _w, _h in _cluster_lines(blocks):
            source = " ".join(b.text for b in line_blocks).strip()
            if not source:
                continue
            target = (line_blocks[0].translated or "").strip()
            lines_out.append(f"[src]        {source}")
            lines_out.append(f"[{target_lang}] {target}")
            lines_out.append("")
        lines_out.append("")

    texts_path = output_dir / "texts.txt"
    texts_path.write_text("\n".join(lines_out), encoding="utf-8")


def run_pipeline(
    url: str | None = None,
    image_dir: Path | None = None,
    target_lang: str = "",
    output_dir: Path = Path("./out"),
    scraper_name: str | None = None,
    ocr_engine: OCREngine | None = None,
    translator: Translator | None = None,
) -> None:
    from image_localizer.ocr.registry import get_ocr_engine
    from image_localizer.scrapers.registry import get_scraper
    from image_localizer.translation.registry import get_translator

    if not url and not image_dir:
        raise ValueError("Either url or image_dir must be provided.")
    if image_dir and not image_dir.exists():
        raise ValueError(f"Image directory does not exist: {image_dir}")

    output_dir = output_dir / target_lang
    originals_dir = output_dir / "originals"
    edited_dir = output_dir / "edited"
    originals_dir.mkdir(parents=True, exist_ok=True)
    edited_dir.mkdir(parents=True, exist_ok=True)

    ocr = ocr_engine or get_ocr_engine("easyocr")
    translator = translator or get_translator("claude")

    if url:
        scraper_name = scraper_name or _detect_scraper_name(url)
        scraper = get_scraper(scraper_name)

        print(f"Fetching {url} ...")
        html = asyncio.run(_fetch_html(url, scraper))

        print(f"Extracting image URLs with {scraper_name} scraper ...")
        assets = scraper.extract_image_urls(html, url)
        if not assets:
            print("No images found.")
            return
        print(f"Found {len(assets)} images.")

        headers = scraper.site_config.get("headers", {})
        print("Downloading images ...")
        downloaded = asyncio.run(download_images(assets, originals_dir, headers=headers))
        print(f"Downloaded {len(downloaded)} images.")
    else:
        assert image_dir is not None
        print(f"Using local images from {image_dir} ...")
        downloaded = _collect_local_images(image_dir)
        # Copy local images into the output originals folder for a consistent output layout.
        copied: list[tuple[ImageAsset, Path]] = []
        for asset, src_path in downloaded:
            dst_path = originals_dir / src_path.name
            shutil.copy2(src_path, dst_path)
            copied.append((asset, dst_path))
        downloaded = copied
        print(f"Found {len(downloaded)} images.")

    print(f"Using OCR: {ocr.name}, Translator: {translator.name}")

    results: list[tuple[ImageAsset, Path, list[TextBlock]]] = []
    for asset, path in downloaded:
        print(f"Extracting text from {path.name} ...")
        blocks = ocr.extract_text(path)
        results.append((asset, path, blocks))

    print("Translating extracted texts ...")
    texts_to_translate = _collect_texts(results)
    if texts_to_translate:
        translated = translator.translate(texts_to_translate, target_lang=target_lang)
        translation_map = dict(zip(texts_to_translate, translated))
        _apply_translations(results, translation_map)

    print("Editing images ...")
    for asset, path, blocks in results:
        out_path = edited_dir / path.name
        edit_image(path, blocks, out_path)
        print(f"Saved edited image: {out_path}")

    _write_manifest(output_dir, url, image_dir, target_lang, results)
    _write_texts(output_dir, target_lang, results)
    print(f"Done. Output: {output_dir}")
