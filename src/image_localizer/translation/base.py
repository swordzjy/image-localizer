from __future__ import annotations

from abc import ABC, abstractmethod


class Translator(ABC):
    @abstractmethod
    def translate(self, texts: list[str], target_lang: str, source_lang: str | None = None) -> list[str]:
        """Translate a list of text strings into the target language."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
