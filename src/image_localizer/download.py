from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from PIL import Image

from image_localizer.models import ImageAsset


async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict[str, str] | None = None) -> str:
    if url.startswith("file://"):
        return _read_local_file(url).decode("utf-8", errors="replace")
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.text()


def _filename_for_url(url: str, idx: int) -> str:
    parsed = urlparse(url)
    path = Path(parsed.path)
    name = path.name or f"image_{idx}"
    # Sanitize
    name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    if not name or name == "image":
        name = f"image_{idx}"
    if not Path(name).suffix:
        name += ".jpg"
    return name


async def _download_one(
    session: aiohttp.ClientSession,
    asset: ImageAsset,
    output_dir: Path,
    idx: int,
) -> Path | None:
    try:
        if asset.url.startswith("file://"):
            data = _read_local_file(asset.url)
        else:
            async with session.get(asset.url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                resp.raise_for_status()
                data = await resp.read()
    except Exception as exc:
        print(f"Failed to download {asset.url}: {exc}")
        return None

    filename = _filename_for_url(asset.url, idx)
    path = output_dir / filename
    # Handle duplicate names
    counter = 1
    stem = path.stem
    suffix = path.suffix
    while path.exists():
        path = output_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    path.write_bytes(data)

    # Validate image
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        print(f"Downloaded file is not a valid image: {path} ({exc})")
        path.unlink(missing_ok=True)
        return None

    return path


def _read_local_file(url: str) -> bytes:
    from urllib.request import url2pathname

    path = Path(url2pathname(urlparse(url).path))
    return path.read_bytes()


async def download_images(
    assets: list[ImageAsset],
    output_dir: Path,
    headers: dict[str, str] | None = None,
    max_concurrent: int = 5,
) -> list[tuple[ImageAsset, Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    connector = aiohttp.TCPConnector(limit=max_concurrent * 2)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        sem = asyncio.Semaphore(max_concurrent)

        async def _wrapped(asset: ImageAsset, idx: int) -> tuple[ImageAsset, Path] | None:
            async with sem:
                path = await _download_one(session, asset, output_dir, idx)
                if path:
                    return asset, path
                return None

        tasks = [_wrapped(asset, i) for i, asset in enumerate(assets)]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
