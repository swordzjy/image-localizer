from __future__ import annotations

from urllib.parse import unquote

from bs4 import BeautifulSoup

from image_localizer.models import ImageAsset
from image_localizer.scrapers.base import SiteScraper


class GenericScraper(SiteScraper):
    def extract_image_urls(self, html: str, page_url: str) -> list[ImageAsset]:
        assets: list[ImageAsset] = []
        seen: set[str] = set()
        soup = BeautifulSoup(html, "html.parser")
        selector = self.site_config.get("selectors", {}).get("visible_img_selector", "img")

        for idx, img in enumerate(soup.select(selector)):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src or src in seen:
                continue
            # Basic filtering of tracking pixels / icons
            lower = src.lower()
            if any(ext in lower for ext in (".svg", ".gif", "1x1", "blank", "spacer")):
                continue
            seen.add(src)
            assets.append(
                ImageAsset(
                    url=self._make_absolute(unquote(src), page_url),
                    alt=img.get("alt", ""),
                    position=idx,
                )
            )

        # Sort by some heuristic: prefer URLs that look like product images
        def _score(asset: ImageAsset) -> int:
            url = asset.url.lower()
            return int("_sl" in url or "image" in url or "product" in url or "zoom" in url)

        assets.sort(key=_score, reverse=True)
        for i, asset in enumerate(assets):
            asset.position = i
        return assets
