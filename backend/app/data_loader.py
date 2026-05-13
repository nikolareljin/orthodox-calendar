from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List

from .models import CalendarEntry

DEFAULT_DATA_FILES = ["oca_julian.json", "neobyzantine_hagiographies.json"]

# Files excluded from directory scans (demo/sample data not for production).
_EXCLUDED_FILENAMES = frozenset({"saints_sample.json"})


def _iter_data_files() -> Iterable[Path]:
    base = Path(__file__).resolve().parent / "data"
    custom_path = os.getenv("ORTHODOX_CALENDAR_DATA_PATH")
    yielded: set[Path] = set()

    def yield_once(path: Path) -> Iterable[Path]:
        resolved = path.resolve()
        if resolved not in yielded and path.name not in _EXCLUDED_FILENAMES:
            yielded.add(resolved)
            yield path

    if custom_path:
        custom = Path(custom_path)
        if custom.is_file():
            yield from yield_once(custom)
        elif custom.is_dir():
            for data_file in sorted(custom.glob("*.json")):
                yield from yield_once(data_file)
            custom_traditions = custom / "traditions"
            if custom_traditions.is_dir():
                for data_file in sorted(custom_traditions.glob("*.json")):
                    yield from yield_once(data_file)

    for filename in DEFAULT_DATA_FILES:
        yield from yield_once(base / filename)

    # Tradition-specific overlay files (auto-discovered)
    traditions_dir = base / "traditions"
    if traditions_dir.is_dir():
        for data_file in sorted(traditions_dir.glob("*.json")):
            yield from yield_once(data_file)


@lru_cache(maxsize=1)
def load_calendar_entries() -> List[CalendarEntry]:
    entries: List[CalendarEntry] = []
    for data_file in _iter_data_files():
        if not data_file.exists():
            continue
        with data_file.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        entries.extend(CalendarEntry(**entry) for entry in raw)
    return entries


def build_index() -> Dict[str, List[CalendarEntry]]:
    """Index entries by tradition for quick lookups."""
    index: Dict[str, List[CalendarEntry]] = {}
    for entry in load_calendar_entries():
        key = entry.tradition.lower()
        index.setdefault(key, []).append(entry)
    return index
