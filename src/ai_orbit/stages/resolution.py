from __future__ import annotations

import copy

from src.ai_orbit.models import Entity, EntityCandidate, EntityMappingLogEntry
from src.ai_orbit.utils.identity import canonical_display_name


def resolve_entities(candidates: list[EntityCandidate]) -> tuple[list[Entity], list[EntityMappingLogEntry], dict[str, str], dict[str, str], int]:
    """Deterministic entity resolution.

    Returns final entities, audit mapping log, raw-source-key to entity-id map,
    raw-source-key to canonical-key map, and duplicate count.
    """
    by_key: dict[str, Entity] = {}
    mapping: list[EntityMappingLogEntry] = []
    source_key_to_id: dict[str, str] = {}
    source_key_to_canonical: dict[str, str] = {}
    duplicates = 0

    for candidate in candidates:
        canonical = candidate.canonical_key
        existing = by_key.get(canonical)
        method = "canonical_url" if ":url:" in canonical else "normalized_name"
        confidence = 1.0 if method == "canonical_url" else 0.92
        reason = "same normalized URL" if method == "canonical_url" else "same normalized name after suffix/alias normalization"

        if existing is None:
            entity = copy.deepcopy(candidate.entity)
            if entity.entity_type == "company":
                entity.name = canonical_display_name(entity.name)
            by_key[canonical] = entity
        else:
            duplicates += 1
            entity = existing
            _merge_entity(entity, candidate.entity)

        source_key_to_id[candidate.raw.source_key] = entity.id
        source_key_to_canonical[candidate.raw.source_key] = canonical
        mapping.append(EntityMappingLogEntry(
            raw_value=candidate.raw.name,
            canonical_value=entity.name,
            method=method,
            confidence=confidence,
            source_url=candidate.raw.source_url,
            raw_source_key=candidate.raw.source_key,
            canonical_id=entity.id,
            reason=reason,
        ))

    return list(by_key.values()), mapping, source_key_to_id, source_key_to_canonical, duplicates


def _merge_entity(target: Entity, incoming: Entity) -> None:
    for category in incoming.categories:
        if category not in target.categories:
            target.categories.append(category)
    for key, value in incoming.metadata.items():
        if key not in target.metadata or target.metadata[key] in ({}, None):
            target.metadata[key] = value
        elif isinstance(target.metadata[key], dict) and isinstance(value, dict):
            for child_key, child_value in value.items():
                if child_key not in target.metadata[key] or target.metadata[key][child_key] in (None, "", [], {}):
                    target.metadata[key][child_key] = child_value
    target.provenance.transformations.append({
        "stage": "resolution",
        "operation": "merged_duplicate_candidate",
        "incoming_source_record_id": incoming.provenance.source_record_id,
        "incoming_source_url": incoming.source.url,
    })
