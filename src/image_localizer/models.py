from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageAsset:
    url: str
    alt: str = ""
    position: int = 0
    is_primary: bool = False
    width: int | None = None
    height: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextBlock:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0
    translated: str | None = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def with_translation(self, translated: str) -> TextBlock:
        return TextBlock(
            text=self.text,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            confidence=self.confidence,
            translated=translated,
        )
