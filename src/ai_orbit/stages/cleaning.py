from __future__ import annotations

import copy
import re

from src.ai_orbit.models import RawEntityRecord
from src.ai_orbit.utils.url import normalize_url


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def clean_records(records: list[RawEntityRecord]) -> list[RawEntityRecord]:
    cleaned: list[RawEntityRecord] = []
    for record in records:
        clone = copy.copy(record)
        clone.name = _clean_text(record.name)
        clone.description = _clean_text(record.description)
        clone.url = normalize_url(record.url)
        clone.source_url = normalize_url(record.source_url)
        # Preserve category order while removing duplicates/empty strings.
        seen: set[str] = set()
        categories: list[str] = []
        for category in record.categories:
            cat = _clean_text(category)
            if cat and cat not in seen:
                categories.append(cat)
                seen.add(cat)
        clone.categories = categories
        cleaned.append(clone)
    return cleaned
