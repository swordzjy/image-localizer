from __future__ import annotations

from image_localizer.translation.base import Translator
from image_localizer.translation.claude_engine import ClaudeTranslator
from image_localizer.translation.openai_engine import OpenAITranslator


def get_translator(name: str) -> Translator:
    name = name.lower()
    if name == "claude":
        return ClaudeTranslator()
    if name == "openai":
        return OpenAITranslator()
    raise ValueError(f"Unsupported translator: {name}. Choose from: claude, openai")


def list_translators() -> list[str]:
    return ["claude", "openai"]
