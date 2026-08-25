from __future__ import annotations

import re
import unicodedata
import uuid

from src.ai_orbit.utils.url import normalize_url

_ORG_SUFFIXES = (
    "incorporated",
    "inc",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "company",
    "co",
)

_ALIAS_TO_CANONICAL = {
    "open ai": "openai",
    "openai": "openai",
    "openai inc": "openai",
    "openai incorporated": "openai",
}

_CANONICAL_DISPLAY = {
    "openai": "OpenAI",
}


def normalize_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name or "")
    value = value.strip().casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[.,'\"`´’()\[\]{}]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if value in _ALIAS_TO_CANONICAL:
        value = _ALIAS_TO_CANONICAL[value]
    tokens = value.split()
    while tokens and tokens[-1] in _ORG_SUFFIXES:
        tokens.pop()
    value = " ".join(tokens)
    if value in _ALIAS_TO_CANONICAL:
        value = _ALIAS_TO_CANONICAL[value]
    return value


def canonical_display_name(name: str) -> str:
    normalized = normalize_name(name)
    if normalized in _CANONICAL_DISPLAY:
        return _CANONICAL_DISPLAY[normalized]
    return re.sub(r"\s+", " ", (name or "").strip())


def stable_uuid(entity_type: str, canonical_identity: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai-orbit:{entity_type}:{canonical_identity}"))


def canonical_key(entity_type: str, name: str, url: str) -> str:
    if entity_type == "company":
        return f"{entity_type}:name:{normalize_name(name)}"
    if entity_type == "task":
        return f"{entity_type}:name:{normalize_name(name)}"
    normalized_url = normalize_url(url)
    if normalized_url:
        return f"{entity_type}:url:{normalized_url}"
    return f"{entity_type}:name:{normalize_name(name)}"
