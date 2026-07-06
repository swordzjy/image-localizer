from __future__ import annotations

import json
import os

from image_localizer.translation.base import Translator


class OpenAITranslator(Translator):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("openai is required. Install with: pip install openai") from exc
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI translator requires OPENAI_API_KEY env var or api_key argument")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    @property
    def name(self) -> str:
        return "openai"

    def translate(self, texts: list[str], target_lang: str, source_lang: str | None = None) -> list[str]:
        if not texts:
            return []
        source_hint = f" from {source_lang}" if source_lang else ""
        system_prompt = (
            "You are a professional translator for e-commerce product images. "
            "Translate the provided text strings accurately, preserving marketing tone and brevity. "
            "Return ONLY a JSON object with a single key 'translations' containing the translated strings in the same order."
        )
        user_prompt = (
            f"Translate the following{source_hint} text strings to {target_lang}:\n\n"
            + "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
            + "\n\nReturn JSON: {\"translations\": [\"...\", \"...\"]}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        content = response.choices[0].message.content or ""
        return _parse_translation_response(content, len(texts), fallback=texts)


def _parse_translation_response(content: str, expected_count: int, fallback: list[str]) -> list[str]:
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1:
        try:
            data = json.loads(content[start : end + 1])
            translations = data.get("translations", [])
            if isinstance(translations, list) and len(translations) == expected_count:
                return [str(t) for t in translations]
        except json.JSONDecodeError:
            pass
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    results: list[str] = []
    for line in lines:
        if "." in line[:4]:
            parts = line.split(".", 1)
            if parts[0].strip().isdigit():
                results.append(parts[1].strip())
    if len(results) == expected_count:
        return results
    return fallback
