from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SiteConfig:
    name: str
    headers: dict[str, str]
    selectors: dict[str, Any]
    min_image_width: int = 300
    min_image_height: int = 300

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteConfig:
        return cls(
            name=data["name"],
            headers=data.get("headers", {}),
            selectors=data.get("selectors", {}),
            min_image_width=data.get("min_image_width", 300),
            min_image_height=data.get("min_image_height", 300),
        )


def _config_dir() -> Path:
    # Support running from source tree or installed package
    src = Path(__file__).resolve().parent
    candidate = src.parent.parent / "configs" / "sites"
    if candidate.exists():
        return candidate
    # Installed package data fallback
    return Path(os.environ.get("IMAGE_LOCALIZER_CONFIG_DIR", str(src / "configs" / "sites")))


def load_site_config(name: str) -> SiteConfig:
    config_dir = _config_dir()
    path = config_dir / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Site config not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SiteConfig.from_dict(data)


def list_site_configs() -> list[str]:
    config_dir = _config_dir()
    return [p.stem for p in config_dir.glob("*.yml")]
