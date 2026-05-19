"""Shared saint-name normalization utilities for import and enrichment scripts.

Logic mirrors backend/app/services/saints.py so off-line scripts produce
consistent match keys without importing the full application package.
"""

from __future__ import annotations

import re

_HONORIFIC_RE = re.compile(
    r"^(?:(?:saint|st\.|st|venerable|blessed|holy|new martyr|hieromartyr|martyr)\s+)+",
    re.IGNORECASE,
)
_EVENT_PREFIX_RE = re.compile(
    r"^(?:(?:translation|uncovering|discovery|opening) of (?:the )?relics of "
    r"|(?:repose|translation|uncovering|discovery|opening) of (?:the )?)+",
    re.IGNORECASE,
)
_DROP_TOKENS = frozenset({
    "saint", "st", "venerable", "blessed", "holy",
    "hieromartyr", "martyr", "new", "righteous",
    "wonderworker", "great", "of", "the",
})


def normalize(value: str) -> str:
    """Return a stable, lower-cased match key from a saint name or title."""
    value = _EVENT_PREFIX_RE.sub("", value.lower().strip())
    value = _HONORIFIC_RE.sub("", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [t for t in value.split() if t not in _DROP_TOKENS]
    return " ".join(tokens)


def slug_key(hagiography_url: str) -> str:
    """Extract the stable OCA ID-slug tail from a hagiography URL."""
    return hagiography_url.rsplit("/", 1)[-1] if hagiography_url else ""


def saint_keys(name: str, title: str | None = None, hagiography_url: str | None = None) -> list[str]:
    """Multiple match aliases for one saint (mirrors services/saints.py:_saint_keys)."""
    candidates = [v for v in [title, name] if v]
    if hagiography_url:
        candidates.append(slug_key(hagiography_url))
    seen: set[str] = set()
    keys: list[str] = []
    for raw in candidates:
        k = normalize(raw)
        if k and k not in seen:
            keys.append(k)
            seen.add(k)
    return keys or [name.lower().strip()]
