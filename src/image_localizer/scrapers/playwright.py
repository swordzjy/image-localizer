from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from image_localizer.models import ImageAsset
from image_localizer.scrapers.base import SiteScraper


class PlaywrightScraper(SiteScraper):
    """Render the page in a headless browser and collect image URLs.

    Requires `playwright` and browser binaries:
        pip install playwright
        playwright install chromium
    """

    def extract_image_urls(self, html: str, page_url: str) -> list[ImageAsset]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ImportError("playwright is required. Install with: pip install playwright") from exc

        assets: list[ImageAsset] = []
        seen: set[str] = set()
        timeout = self.site_config.get("playwright_timeout", 30_000)
        wait_selector = self.site_config.get("selectors", {}).get("wait_for", "img")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=self.site_config.get("headers", {}).get("User-Agent"),
                viewport={"width": 1280, "height": 800},
            )
            page.goto(page_url, wait_until="networkidle", timeout=timeout)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout // 2)
                except Exception:
                    pass

            # Try to read Amazon's colorImages object from JS context
            try:
                color_images = page.evaluate("() => (typeof colorImages !== 'undefined' ? colorImages : null)")
                if isinstance(color_images, dict):
                    for sub in ("initial", "variant"):
                        for idx, img in enumerate(color_images.get(sub, [])):
                            url = img.get("hiRes") or img.get("large") or img.get("mainUrl")
                            if url and url not in seen:
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
            except Exception:
                pass

            # Fallback to DOM images
            if not assets:
                soup = BeautifulSoup(page.content(), "html.parser")
                for idx, img in enumerate(soup.find_all("img")):
                    src = img.get("src") or img.get("data-src") or img.get("data-old-hires")
                    if not src or src in seen:
                        continue
                    seen.add(src)
                    assets.append(
                        ImageAsset(
                            url=self._make_absolute(src, page_url),
                            alt=img.get("alt", ""),
                            position=idx,
                        )
                    )
            browser.close()

        # Filter by size hints
        filtered: list[ImageAsset] = []
        min_w = self.site_config.get("min_image_width", 300)
        min_h = self.site_config.get("min_image_height", 300)
        for asset in assets:
            w = asset.width or min_w
            h = asset.height or min_h
            if w >= min_w and h >= min_h:
                filtered.append(asset)
        for i, asset in enumerate(filtered):
            asset.position = i
        return filtered
