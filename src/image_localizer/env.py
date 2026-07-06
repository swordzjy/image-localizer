"""Minimal, dependency-free ``.env`` loader.

Reads ``KEY=VALUE`` pairs from a ``.env`` file and populates ``os.environ`` so
that API keys (e.g. ``ANTHROPIC_API_KEY``) can be stored in a project-local
``.env`` instead of being exported manually. Existing environment variables take
precedence and are never overwritten.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_dotenv(start: Path | None = None) -> Path | None:
    """Search ``start`` and its parents for a ``.env`` file.

    Walks upward from ``start`` (default: current working directory) to the
    filesystem root, returning the first ``.env`` found, or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``.env`` file contents into a mapping.

    Supports ``KEY=VALUE`` lines, ``# comments``, blank lines, an optional
    leading ``export`` keyword, and surrounding single/double quotes on values.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_dotenv(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load a ``.env`` file into ``os.environ``.

    Args:
        path: Explicit ``.env`` path. When omitted, searches upward from the
            current working directory.
        override: When ``False`` (default), variables already present in the
            environment are left untouched.

    Returns:
        The mapping of keys that were applied to ``os.environ``.
    """
    dotenv_path = path or find_dotenv()
    if dotenv_path is None or not dotenv_path.is_file():
        return {}

    parsed = parse_dotenv(dotenv_path.read_text(encoding="utf-8"))
    applied: dict[str, str] = {}
    for key, value in parsed.items():
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied
