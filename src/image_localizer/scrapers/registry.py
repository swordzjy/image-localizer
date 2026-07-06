from __future__ import annotations

from image_localizer.config import load_site_config
from image_localizer.scrapers.amazon import AmazonScraper
from image_localizer.scrapers.base import SiteScraper
from image_localizer.scrapers.generic import GenericScraper
from image_localizer.scrapers.playwright import PlaywrightScraper

_REGISTRY: dict[str, type[SiteScraper]] = {
    "amazon": AmazonScraper,
    "generic": GenericScraper,
    "playwright": PlaywrightScraper,
}


def get_scraper(name: str) -> SiteScraper:
    config = load_site_config(name)
    cls = _REGISTRY.get(name, GenericScraper)
    return cls(config.__dict__)


def list_scrapers() -> list[str]:
    return list(_REGISTRY.keys())
