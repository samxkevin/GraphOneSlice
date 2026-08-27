"""Read-only final submission audit for committed artifacts.

This script makes no network calls and does not modify data. It is intended for
reviewers and CI-like local verification of the metrics reported in the README.
"""
from __future__ import annotations

import csv
from collections import Counter
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return [item for item in payload["records"] if isinstance(item, dict)]
    return []


def duplicate_values(values: list[Any]) -> list[Any]:
    return sorted(value for value, count in Counter(values).items() if value is not None and count > 1)


def csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    entities = records(read_json(ROOT / "data" / "entities.json"))
    relationships = records(read_json(ROOT / "data" / "relationships.json"))
    ai_report = read_json(ROOT / "data" / "validation_report.json")
    ai_mapping = records(read_json(ROOT / "data" / "entity_mapping_log.json"))
    feasibility = records(read_json(ROOT / "data" / "source_feasibility.json"))
    entity_ids = {entity.get("id") for entity in entities}
    invalid_endpoints = [
        relationship.get("id")
        for relationship in relationships
        if relationship.get("source_entity_id") not in entity_ids
        or relationship.get("target_entity_id") not in entity_ids
    ]

    graph_root = ROOT / "data" / "graphone"
    graph_report = read_json(graph_root / "validation_report.json")
    graph_tabs = {
        name: records(read_json(graph_root / f"{name}.json"))
        for name in ("startups", "products", "research_papers", "jobs", "news")
    }
    graph_mapping = records(read_json(graph_root / "entity_mapping_log.json"))
    graph_csv = {
        path.stem: csv_row_count(path)
        for path in sorted((graph_root / "sheets").glob("*.csv"))
    }

    research_csv = ROOT / "ResearchPaperSpreadsheetsAvailableForOfflineView" / "GraphOneSliceResearchPapers(FirstOneThousandEntries).csv"
    with research_csv.open("r", encoding="utf-8", newline="") as handle:
        research_rows = list(csv.DictReader(handle))

    result = {
        "required_paths_present": all(
            path.exists()
            for path in (
                ROOT / "README.md",
                ROOT / "src",
                ROOT / "data",
                ROOT / "run.py",
                ROOT / "reviewer_app.py",
                ROOT / "GraphOneSliceSystemArchitecture.pdf",
            )
        ),
        "ai_orbit": {
            "entities": len(entities),
            "relationships": len(relationships),
            "entity_types": dict(sorted(Counter(entity.get("entity_type") for entity in entities).items())),
            "categories": dict(sorted(Counter(category for entity in entities for category in entity.get("categories", [])).items())),
            "entity_sources": dict(sorted(Counter((entity.get("source") or {}).get("name") for entity in entities).items())),
            "relationship_types": dict(sorted(Counter(relationship.get("relationship_type") for relationship in relationships).items())),
            "validation_status": ai_report.get("status"),
            "validation_failures": len(ai_report.get("failures", [])),
            "rejected_records": len(ai_report.get("rejected_records", [])),
            "warnings": len(ai_report.get("warnings", [])),
            "source_failures": len(ai_report.get("source_failures", [])),
            "provenance_missing": sum(not entity.get("provenance") for entity in entities),
            "relationship_evidence_missing": sum(not relationship.get("evidence") for relationship in relationships),
            "duplicate_entity_ids": duplicate_values([entity.get("id") for entity in entities]),
            "duplicate_relationship_ids": duplicate_values([relationship.get("id") for relationship in relationships]),
            "invalid_relationship_endpoints": invalid_endpoints,
            "mapping_entries": len(ai_mapping),
            "feasibility_statuses": dict(sorted(Counter(entry.get("status") for entry in feasibility).items())),
        },
        "graphone": {
            "validation_status": graph_report.get("status"),
            "validation_failures": len(graph_report.get("failures", [])),
            "summary": graph_report.get("summary"),
            "record_counts": {name: len(value) for name, value in graph_tabs.items()},
            "provenance_missing": {
                name: sum(not record.get("provenance") for record in values)
                for name, values in graph_tabs.items()
            },
            "mapping_entries": len(graph_mapping),
            "csv_row_counts": graph_csv,
            "fresh_news_timestamp_semantics": sorted({record.get("timestamp_semantics") for record in graph_tabs["news"]}),
        },
        "research_export": {
            "rows": len(research_rows),
            "unique_paper_urls": len({row.get("paper_url") for row in research_rows}),
            "missing_required": {
                column: sum(not (row.get(column) or "").strip() for row in research_rows)
                for column in ("source_url", "title", "authors", "paper_url", "published_date", "collectedAt")
            },
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - executable audit utility
    raise SystemExit(main())
