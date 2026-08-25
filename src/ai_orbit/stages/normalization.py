from __future__ import annotations

from src.ai_orbit.models import Entity, EntityCandidate, Provenance, RawEntityRecord, SourceRef
from src.ai_orbit.utils.identity import canonical_key, normalize_name, stable_uuid
from src.ai_orbit.utils.url import normalize_url


def normalize_records(records: list[RawEntityRecord]) -> list[EntityCandidate]:
    candidates: list[EntityCandidate] = []
    for record in records:
        normalized_name = normalize_name(record.name)
        normalized_url = normalize_url(record.url)
        key = canonical_key(record.entity_type, record.name, normalized_url)
        entity_id = stable_uuid(record.entity_type, key)
        transformations = [
            {"stage": "cleaning", "operation": "trim_collapse_whitespace_and_normalize_url"},
            {"stage": "normalization", "operation": "normalize_name", "input": record.name, "output": normalized_name},
            {"stage": "normalization", "operation": "canonical_key", "output": key},
        ]
        entity = Entity(
            id=entity_id,
            entity_type=record.entity_type,
            name=record.name,
            description=record.description,
            url=normalized_url,
            categories=record.categories,
            source=SourceRef(name=record.source_name, url=record.source_url),
            metadata=record.metadata,
            provenance=Provenance(
                discovered_by=record.source_name,
                source_url=record.source_url,
                source_record_id=record.source_key,
                observed_fields=_observed_fields(record),
                transformations=transformations,
                fetched_at=record.fetched_at.isoformat() if record.fetched_at else None,
            ),
        )
        candidates.append(EntityCandidate(raw=record, normalized_name=normalized_name, normalized_url=normalized_url, canonical_key=key, entity=entity))
    return candidates


def _observed_fields(record: RawEntityRecord) -> dict[str, object]:
    fields: dict[str, object] = {
        "name": record.name,
        "description": record.description,
        "url": record.url,
        "categories": record.categories,
    }
    for key, value in record.metadata.items():
        fields[key] = value
    return fields
