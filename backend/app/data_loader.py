from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List

from .models import CalendarEntry

DEFAULT_DATA_FILES = ["saints_sample.json"]


def _iter_data_files() -> Iterable[Path]:
    base = Path(__file__).resolve().parent / "data"
    custom_path = os.getenv("ORTHODOX_CALENDAR_DATA_PATH")
    if custom_path:
        custom = Path(custom_path)
        if custom.is_file():
            yield custom
        elif custom.is_dir():
            yield from sorted(custom.glob("*.json"))

    for filename in DEFAULT_DATA_FILES:
        yield base / filename


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
