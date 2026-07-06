from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from image_localizer.models import TextBlock


class OCREngine(ABC):
    @abstractmethod
    def extract_text(self, image_path: Path) -> list[TextBlock]:
        """Return detected text blocks with bounding boxes."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
