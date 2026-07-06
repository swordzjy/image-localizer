from __future__ import annotations

import json
import os

from image_localizer.translation.base import Translator

# Models to try if the configured/default model is not available for the key.
# Newer Claude 4/5 IDs come first; legacy Claude 3 IDs are kept for older keys.
FALLBACK_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


class ClaudeTranslator(Translator):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        try:
            from anthropic import Anthropic, NotFoundError
        except ImportError as exc:
            raise ImportError("anthropic is required. Install with: pip install anthropic") from exc
        self.NotFoundError = NotFoundError
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Claude translator requires ANTHROPIC_API_KEY env var or api_key argument")
        self.client = Anthropic(api_key=self.api_key)
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or FALLBACK_MODELS[0]

    @property
    def name(self) -> str:
        return "claude"

    def _call_model(self, model: str, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

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
            + '\n\nReturn JSON: {"translations": ["...", "..."]}'
        )

        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last_error: Exception | None = None
        for model in models_to_try:
            try:
                content = self._call_model(model, system_prompt, user_prompt)
                return _parse_translation_response(content, len(texts), fallback=texts)
            except self.NotFoundError as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise last_error


def _parse_translation_response(content: str, expected_count: int, fallback: list[str]) -> list[str]:
    # Try to find JSON block
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
    # Fallback: numbered list parsing
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
