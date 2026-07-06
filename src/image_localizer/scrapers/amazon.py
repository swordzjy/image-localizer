from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup

from image_localizer.models import ImageAsset
from image_localizer.scrapers.base import SiteScraper


class AmazonScraper(SiteScraper):
    def extract_image_urls(self, html: str, page_url: str) -> list[ImageAsset]:
        assets: list[ImageAsset] = []
        seen: set[str] = set()

        # 1. Try to parse colorImages / ImageBlockATF JSON blobs
        for key in self.site_config.get("selectors", {}).get("image_data_keys", ["colorImages"]):
            assets.extend(self._extract_from_json_key(html, page_url, key, seen))

        # 2. Fallback: data-old-hires, data-a-dynamic-image attributes
        for attr in self.site_config.get("selectors", {}).get("fallback_attributes", ["data-old-hires", "src"]):
            assets.extend(self._extract_from_img_attrs(html, page_url, attr, seen))

        # 3. Last resort: visible img tags
        assets.extend(self._extract_from_visible_imgs(html, page_url, seen))

        # Deduplicate and filter by size hints if available
        filtered: list[ImageAsset] = []
        min_w = self.site_config.get("min_image_width", 400)
        min_h = self.site_config.get("min_image_height", 400)
        for asset in assets:
            if asset.url in seen:
                continue
            seen.add(asset.url)
            w = asset.width or min_w
            h = asset.height or min_h
            if w >= min_w and h >= min_h:
                filtered.append(asset)

        # Stable ordering
        for i, asset in enumerate(filtered):
            asset.position = i
        return filtered

    def _extract_from_json_key(self, html: str, page_url: str, key: str, seen: set[str]) -> list[ImageAsset]:
        assets: list[ImageAsset] = []
        pattern = re.compile(rf"{re.escape(key)}['\"]?\s*[:=]\s*(\{{.*?\}});", re.DOTALL)
        for match in pattern.finditer(html):
            raw = match.group(1)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            images: list[dict[str, Any]] = []
            if isinstance(data, dict):
                # Amazon colorImages shape: { initial: [...], variant: [...] }
                for sub in ("initial", "variant"):
                    if isinstance(data.get(sub), list):
                        images.extend(data[sub])
            elif isinstance(data, list):
                images.extend(data)
            for idx, img in enumerate(images):
                if not isinstance(img, dict):
                    continue
                url = img.get("hiRes") or img.get("large") or img.get("mainUrl") or img.get("landscapeUrl")
                if not url or url in seen:
                    continue
                seen.add(url)
                assets.append(
                    ImageAsset(
                        url=self._make_absolute(url, page_url),
                        alt=img.get("alt", ""),
                        position=idx,
                        is_primary=idx == 0,
                        width=img.get("width"),
                        height=img.get("height"),
                    )
                )
        return assets

    def _extract_from_img_attrs(self, html: str, page_url: str, attr: str, seen: set[str]) -> list[ImageAsset]:
        assets: list[ImageAsset] = []
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            value = img.get(attr)
            if not value:
                continue
            if attr == "data-a-dynamic-image" and value.startswith("{"):
                try:
                    variants = json.loads(value)
                    # variants is {"url": [width, height], ...}
                    url = max(variants.items(), key=lambda kv: kv[1][0] * kv[1][1])[0]
                    width, height = variants[url]
                except Exception:
                    url = value
                    width = height = None
            else:
                url = value
                width = height = None
            if not url or url in seen:
                continue
            # Ignore tiny icons/spacers
            if width is not None and width < self.site_config.get("min_image_width", 400):
                continue
            if height is not None and height < self.site_config.get("min_image_height", 400):
                continue
            seen.add(url)
            assets.append(
                ImageAsset(
                    url=self._make_absolute(unquote(url), page_url),
                    alt=img.get("alt", ""),
                    width=width,
                    height=height,
                )
            )
        return assets

    def _extract_from_visible_imgs(self, html: str, page_url: str, seen: set[str]) -> list[ImageAsset]:
        assets: list[ImageAsset] = []
        soup = BeautifulSoup(html, "html.parser")
        selector = self.site_config.get("selectors", {}).get("visible_img_selector", "img")
        for idx, img in enumerate(soup.select(selector)):
            src = img.get("src")
            if not src or src in seen:
                continue
            seen.add(src)
            assets.append(
                ImageAsset(
                    url=self._make_absolute(unquote(src), page_url),
                    alt=img.get("alt", ""),
                    position=idx,
                )
            )
        return assets
