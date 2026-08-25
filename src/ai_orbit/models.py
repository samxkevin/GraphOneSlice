from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


REQUIRED_CATEGORIES: set[str] = {
    "Tools",
    "Tasks",
    "Companies",
    "News",
    "Videos",
    "Robots",
    "Devices",
    "Models",
    "Repositories",
    "MCP",
    "Collections",
    "Personal",
    "Products",
    "Creative",
    "New/Recently Added",
}

SUPPORTED_ENTITY_TYPES: set[str] = {
    "tool",
    "task",
    "company",
    "news",
    "video",
    "robot",
    "device",
    "model",
    "repository",
    "mcp",
    "collection",
    "personal",
    "product",
    "creative",
}

SUPPORTED_RELATIONSHIP_TYPES: set[str] = {
    "develops",
    "solves",
    "integrates_with",
    "runs",
    "published_by",
    "hosts",
}


class SourceRef(BaseModel):
    name: str
    url: str


class Provenance(BaseModel):
    discovered_by: str
    source_url: str
    source_record_id: str
    observed_fields: dict[str, Any] = Field(default_factory=dict)
    transformations: list[dict[str, Any]] = Field(default_factory=list)
    fetched_at: str | None = None


class Entity(BaseModel):
    id: str
    entity_type: str
    name: str
    description: str
    url: str
    categories: list[str]
    source: SourceRef
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @field_validator("categories")
    @classmethod
    def categories_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("categories must not be empty")
        return value


class Relationship(BaseModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    evidence: dict[str, Any]
    source: SourceRef
    confidence: float = 1.0
    method: str


class EntityMappingLogEntry(BaseModel):
    raw_value: str
    canonical_value: str
    method: str
    confidence: float
    source_url: str
    raw_source_key: str
    canonical_id: str
    reason: str


class SourceFeasibility(BaseModel):
    source_name: str
    source_type: str
    access_method: str
    url: str
    status: Literal["usable", "unusable", "partial"]
    domain: str | None = None
    http_status: int | None = None
    pagination: str | None = None
    available_fields: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    authentication_required: bool | None = None
    rate_limit_observed: dict[str, str] = Field(default_factory=dict)
    freshness: str | None = None
    anti_bot_js: str | None = None
    inventory_evidence: str | None = None
    company_identity_quality: str | None = None
    ai_relevance: str | None = None
    actual_crawl_feasibility: str | None = None
    record_volume_estimate: str | None = None
    failure_behavior: str | None = None
    yielded_usable_records: int = 0
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class RawEntityRecord:
    source_key: str
    entity_type: str
    name: str
    description: str
    url: str
    categories: list[str]
    source_name: str
    source_url: str
    raw: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    pending_relationships: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: datetime | None = None


@dataclass(slots=True)
class EntityCandidate:
    raw: RawEntityRecord
    normalized_name: str
    normalized_url: str
    canonical_key: str
    entity: Entity


@dataclass(slots=True)
class PipelineState:
    raw_records: list[RawEntityRecord] = field(default_factory=list)
    cleaned_records: list[RawEntityRecord] = field(default_factory=list)
    candidates: list[EntityCandidate] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    mapping_log: list[EntityMappingLogEntry] = field(default_factory=list)
    source_feasibility: list[SourceFeasibility] = field(default_factory=list)
    source_failures: list[dict[str, Any]] = field(default_factory=list)
    rejected_records: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
