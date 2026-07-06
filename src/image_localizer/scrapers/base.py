from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from image_localizer.models import ImageAsset


class SiteScraper(ABC):
    def __init__(self, site_config: dict[str, Any]) -> None:
        self.site_config = site_config

    @abstractmethod
    def extract_image_urls(self, html: str, page_url: str) -> list[ImageAsset]:
        """Extract image URLs from the page HTML."""
        ...

    def _make_absolute(self, url: str, page_url: str) -> str:
        from urllib.parse import urljoin

        return urljoin(page_url, url)
