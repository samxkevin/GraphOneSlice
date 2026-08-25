from src.ai_orbit.models import Entity, Provenance, Relationship, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def _entity(entity_id: str = "entity-1", **overrides):
    payload = {
        "id": entity_id,
        "entity_type": "tool",
        "name": "Observed Tool",
        "description": "A real observed tool description.",
        "url": "https://example.com/tool",
        "categories": ["Tools"],
        "source": SourceRef(name="fixture", url="https://example.com/source"),
        "metadata": {},
        "provenance": Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:tool",
            observed_fields={"name": "Observed Tool"},
        ),
    }
    payload.update(overrides)
    return Entity(**payload)


def test_missing_source_provenance_fails_validation():
    entity = _entity(source=SourceRef(name="", url=""))
    accepted, _relationships, report = validate_outputs([entity], [])
    assert accepted == []
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["missing_provenance"] >= 1


def test_relationship_referencing_missing_entity_fails_validation():
    entity = _entity()
    relationship = Relationship(
        id="rel-1",
        source_entity_id=entity.id,
        target_entity_id="missing-target",
        relationship_type="solves",
        evidence={"observed_value": "topic:agents"},
        source=SourceRef(name="fixture", url="https://example.com/source"),
        method="fixture",
    )
    _entities, relationships, report = validate_outputs([entity], [relationship])
    assert relationships == []
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["relationship_missing_entity"] == 1


def test_malformed_entity_fails_schema_and_business_validation():
    entity = _entity(name="", description="")
    accepted, _relationships, report = validate_outputs([entity], [])
    assert accepted == []
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["missing_required_field"] == 2


def test_shared_evidence_url_warning_is_not_suppressed_for_task_entities():
    tool = _entity(entity_id="tool-1", url="https://example.com/source", name="Observed MCP", entity_type="mcp", categories=["MCP"], metadata={"mcp": {"installation_method": "npm", "runtime_requirements": None}})
    task = _entity(
        entity_id="task-1",
        url="https://example.com/source",
        name="filesystem access",
        entity_type="task",
        categories=["Tasks"],
        metadata={"task": {"url_role": "evidence_source_url"}},
    )
    accepted, _relationships, report = validate_outputs([tool, task], [])
    assert len(accepted) == 2
    assert report["status"] == "passed"
    assert report["summary"]["duplicate_url_count"] == 1
    assert report["warnings"][0]["type"] == "shared_evidence_url"
    assert report["warnings"][0]["entity_count"] == 2
