from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ai_orbit.models import Entity, EntityMappingLogEntry, Relationship, SourceFeasibility


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_outputs(
    output_dir: str | Path,
    *,
    entities: list[Entity],
    relationships: list[Relationship],
    mapping_log: list[EntityMappingLogEntry],
    validation_report: dict[str, Any],
    source_feasibility: list[SourceFeasibility],
) -> None:
    root = Path(output_dir)
    entity_payload = [entity.model_dump(mode="json") for entity in sorted(entities, key=lambda item: (item.entity_type, item.name.lower(), item.id))]
    relationship_payload = [rel.model_dump(mode="json") for rel in sorted(relationships, key=lambda item: item.id)]
    mapping_payload = [entry.model_dump(mode="json") for entry in mapping_log]
    source_payload = [entry.model_dump(mode="json") for entry in source_feasibility]

    _dump_json(root / "entities.json", entity_payload)
    _dump_json(root / "relationships.json", relationship_payload)
    _dump_json(root / "entity_mapping_log.json", mapping_payload)
    _dump_json(root / "validation_report.json", validation_report)
    _dump_json(root / "source_feasibility.json", source_payload)

    categories_dir = root / "categories"
    by_category: dict[str, list[dict[str, Any]]] = {}
    for entity in entity_payload:
        for category in entity.get("categories", []):
            by_category.setdefault(category, []).append(entity)
    for category, rows in by_category.items():
        safe = category.lower().replace("/", "_").replace(" ", "_")
        _dump_json(categories_dir / f"{safe}.json", rows)
