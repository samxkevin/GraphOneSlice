from __future__ import annotations

from collections import Counter
from datetime import datetime
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


def _is_iso_timestamp(value: str) -> bool:
    """Return True when ``value`` is a parseable ISO-8601 timestamp."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


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
    entities_by_url: dict[str, list[Entity]] = {}

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
        normalized_url = normalize_url(entity.url)
        url_counts[normalized_url] += 1
        entities_by_url.setdefault(normalized_url, []).append(entity)
        accepted_entities.append(entity)

    duplicate_urls = [url for url, count in url_counts.items() if count > 1]
    warnings: list[dict[str, Any]] = []
    for url in duplicate_urls:
        warnings.append(_duplicate_url_warning(url, entities_by_url[url]))

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


def _duplicate_url_warning(url: str, entities: list[Entity]) -> dict[str, Any]:
    group = [
        {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "source_record_id": entity.provenance.source_record_id if entity.provenance else None,
            "url_role": ((entity.metadata or {}).get("task") or {}).get("url_role"),
        }
        for entity in entities
    ]
    has_evidence_task = any(item.get("entity_type") == "task" and item.get("url_role") == "evidence_source_url" for item in group)
    warning_type = "shared_evidence_url" if has_evidence_task else "duplicate_url"
    reason = (
        "At least one task entity uses the URL as an evidence source because no canonical task URL was observed."
        if has_evidence_task
        else "Multiple accepted entities have the same normalized entity URL; inspect for possible identity conflation."
    )
    return {
        "type": warning_type,
        "record_id": None,
        "url": url,
        "entity_count": len(entities),
        "entities": group,
        "message": f"shared normalized URL observed: {url}",
        "reason": reason,
    }


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
    product = entity.metadata.get("product") if entity.metadata else None
    if entity.entity_type == "product" and not product:
        failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "product metadata required for product entities"})
    if entity.entity_type == "product" and product:
        if not product.get("canonical_url") or not is_valid_http_url(product.get("canonical_url")):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "product.canonical_url required"})
        if not product.get("ai_relevance_evidence"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "product.ai_relevance_evidence required"})
    robot = entity.metadata.get("robot") if entity.metadata else None
    if entity.entity_type == "robot" and not robot:
        failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "robot metadata required for robot entities"})
    if entity.entity_type == "robot" and robot:
        if not robot.get("catalog_url") or not is_valid_http_url(robot.get("catalog_url")):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "robot.catalog_url required"})
        if not robot.get("identity_evidence"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "robot.identity_evidence required"})
    news = entity.metadata.get("news") if entity.metadata else None
    if entity.entity_type == "news" and not news:
        failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news metadata required for news entities"})
    if entity.entity_type == "news" and news:
        if not news.get("canonical_url") or not is_valid_http_url(news.get("canonical_url")):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news.canonical_url required"})
        published_at = news.get("published_at")
        if not isinstance(published_at, str) or not _is_iso_timestamp(published_at):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news.published_at must be a source-backed ISO-8601 timestamp"})
        if not news.get("timestamp_semantics"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news.timestamp_semantics required"})
        publisher = news.get("publisher")
        if not isinstance(publisher, dict) or not publisher.get("login"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news.publisher.login required"})
        if not news.get("ai_relevance_evidence"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "news.ai_relevance_evidence required"})
    model = entity.metadata.get("model") if entity.metadata else None
    if entity.entity_type == "model" and not model:
        failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "model metadata required for model entities"})
    if entity.entity_type == "model" and model:
        for key in ["license", "modalities", "provider"]:
            if key in model and model[key] is not None and not isinstance(model[key], (str, list)):
                failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": f"model.{key} invalid"})
        if not model.get("provider"):
            failures.append({"type": "invalid_metadata", "record_id": entity.id, "message": "model.provider required when source evidence supplies provider"})
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
