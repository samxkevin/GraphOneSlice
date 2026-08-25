from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import ValidationError

from src.ai_orbit.models import (
    REQUIRED_CATEGORIES,
    SUPPORTED_ENTITY_TYPES,
    SUPPORTED_RELATIONSHIP_TYPES,
    Entity,
    Relationship,
)
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url

# Exported for tests and README clarity.
SUPPORTED_CATEGORIES = REQUIRED_CATEGORIES


def validate_outputs(
    entities: list[Entity],
    relationships: list[Relationship],
    *,
    metrics: dict[str, Any] | None = None,
    source_failures: list[dict[str, Any]] | None = None,
    source_feasibility: list[dict[str, Any]] | None = None,
    rejected_records: list[dict[str, Any]] | None = None,
) -> tuple[list[Entity], list[Relationship], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    accepted_entities: list[Entity] = []
    seen_ids: set[str] = set()
    url_counts: Counter[str] = Counter()

    for entity in entities:
        try:
            Entity.model_validate(entity.model_dump())
        except ValidationError as exc:
            failures.append({"type": "schema_validation", "record_id": getattr(entity, "id", None), "message": str(exc)})
            continue
        entity_failures = _validate_entity(entity, seen_ids)
        if entity_failures:
            failures.extend(entity_failures)
            continue
        seen_ids.add(entity.id)
        url_counts[normalize_url(entity.url)] += 1
        accepted_entities.append(entity)

    duplicate_urls = [url for url, count in url_counts.items() if count > 1]
    warnings: list[dict[str, Any]] = []
    for url in duplicate_urls:
        warnings.append({"type": "duplicate_url", "record_id": None, "message": f"duplicate normalized URL observed: {url}"})

    accepted_ids = {entity.id for entity in accepted_entities}
    accepted_relationships: list[Relationship] = []
    for relationship in relationships:
        try:
            Relationship.model_validate(relationship.model_dump())
        except ValidationError as exc:
            failures.append({"type": "relationship_schema", "record_id": getattr(relationship, "id", None), "message": str(exc)})
            continue
        rel_failures = _validate_relationship(relationship, accepted_ids)
        if rel_failures:
            failures.extend(rel_failures)
            continue
        accepted_relationships.append(relationship)

    per_source = Counter(entity.source.name for entity in accepted_entities)
    per_category = Counter(category for entity in accepted_entities for category in entity.categories)
    per_type = Counter(entity.entity_type for entity in accepted_entities)
    failure_counts = Counter(failure["type"] for failure in failures)
    provenance_count = sum(1 for entity in accepted_entities if entity.provenance and entity.provenance.source_url)

    report = {
        "status": "passed" if not failures else "failed",
        "summary": {
            "total_discovered": (metrics or {}).get("total_discovered"),
            "total_extracted": (metrics or {}).get("total_extracted"),
            "total_cleaned": (metrics or {}).get("total_cleaned"),
            "total_normalized": (metrics or {}).get("total_normalized"),
            "total_deduplicated": len(accepted_entities),
            "total_classified": len(accepted_entities),
            "total_relationships": len(accepted_relationships),
            "total_valid": len(accepted_entities),
            "total_rejected": len(failures) + len(rejected_records or []),
            "duplicate_url_count": len(duplicate_urls),
            "provenance_coverage": provenance_count / len(accepted_entities) if accepted_entities else 0.0,
        },
        "per_source_counts": dict(sorted(per_source.items())),
        "per_category_counts": dict(sorted(per_category.items())),
        "per_entity_type_counts": dict(sorted(per_type.items())),
        "failure_counts_by_type": dict(sorted(failure_counts.items())),
        "warnings": warnings,
        "failures": failures,
        "source_failures": source_failures or [],
        "source_feasibility": source_feasibility or [],
        "rejected_records": rejected_records or [],
    }
    return accepted_entities, accepted_relationships, report


def _validate_entity(entity: Entity, seen_ids: set[str]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if entity.id in seen_ids:
        failures.append({"type": "duplicate_entity", "record_id": entity.id, "message": "duplicate entity id"})
    for field in ["entity_type", "name", "description", "url"]:
        value = getattr(entity, field)
        if not isinstance(value, str) or not value.strip():
            failures.append({"type": "missing_required_field", "record_id": entity.id, "message": f"missing or empty {field}"})
    if entity.entity_type not in SUPPORTED_ENTITY_TYPES:
        failures.append({"type": "unsupported_entity_type", "record_id": entity.id, "message": entity.entity_type})
    unsupported_categories = [cat for cat in entity.categories if cat not in SUPPORTED_CATEGORIES]
    if unsupported_categories:
        failures.append({"type": "unsupported_category", "record_id": entity.id, "message": ", ".join(unsupported_categories)})
    if not is_valid_http_url(entity.url):
        failures.append({"type": "invalid_url", "record_id": entity.id, "message": entity.url})
    if not entity.source or not entity.source.name or not is_valid_http_url(entity.source.url):
        failures.append({"type": "missing_provenance", "record_id": entity.id, "message": "source name/url required"})
    if not entity.provenance or not entity.provenance.source_record_id or not is_valid_http_url(entity.provenance.source_url):
        failures.append({"type": "missing_provenance", "record_id": entity.id, "message": "provenance source record/source url required"})

    failures.extend(_validate_metadata(entity))
    return failures


def _validate_metadata(entity: Entity) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    repo = entity.metadata.get("repository") if entity.metadata else None
    if repo:
        stars = repo.get("stars")
        if stars is not None and (not isinstance(stars, int) or stars < 0):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "repository.stars must be non-negative int/null"})
        if repo.get("last_updated_timestamp") is not None and not isinstance(repo.get("last_updated_timestamp"), str):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "repository.last_updated_timestamp must be string/null"})
    mcp = entity.metadata.get("mcp") if entity.metadata else None
    if entity.entity_type == "mcp" and not mcp:
        failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "mcp metadata required for MCP entities"})
    company = entity.metadata.get("company") if entity.metadata else None
    if company:
        founding = company.get("founding_year")
        if founding is not None and (not isinstance(founding, int) or founding < 1800):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "company.founding_year invalid"})
    model = entity.metadata.get("model") if entity.metadata else None
    if entity.entity_type == "model" and model:
        for key in ["license", "modalities", "provider"]:
            if key in model and model[key] is not None and not isinstance(model[key], (str, list)):
                failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": f"model.{key} invalid"})
    return failures


def _validate_relationship(relationship: Relationship, accepted_ids: set[str]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if relationship.relationship_type not in SUPPORTED_RELATIONSHIP_TYPES:
        failures.append({"type": "malformed_relationship", "record_id": relationship.id, "message": f"unsupported relationship type {relationship.relationship_type}"})
    if relationship.source_entity_id not in accepted_ids:
        failures.append({"type": "relationship_missing_entity", "record_id": relationship.id, "message": f"missing source entity {relationship.source_entity_id}"})
    if relationship.target_entity_id not in accepted_ids:
        failures.append({"type": "relationship_missing_entity", "record_id": relationship.id, "message": f"missing target entity {relationship.target_entity_id}"})
    if relationship.source_entity_id == relationship.target_entity_id:
        failures.append({"type": "malformed_relationship", "record_id": relationship.id, "message": "self relationship is not allowed"})
    if not relationship.evidence:
        failures.append({"type": "malformed_relationship", "record_id": relationship.id, "message": "relationship evidence required"})
    if not relationship.source or not relationship.source.name or not is_valid_http_url(relationship.source.url):
        failures.append({"type": "missing_provenance", "record_id": relationship.id, "message": "relationship source name/url required"})
    return failures
