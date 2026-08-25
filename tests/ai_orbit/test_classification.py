from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.classification import classify_and_create_tasks


def _entity(entity_id: str, *, description: str, metadata=None, entity_type="tool"):
    return Entity(
        id=entity_id,
        entity_type=entity_type,
        name="Fixture",
        description=description,
        url=f"https://example.com/{entity_id}",
        categories=["Tools"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata=metadata or {},
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id=entity_id,
            observed_fields={"description": description},
        ),
    )


def test_task_mapping_skips_derived_integration_target_tools():
    entity = _entity(
        "github-api",
        description="The NPM package description explicitly identifies the GitHub API as the integration target.",
        metadata={"tool": {"derived_role": "integration_target", "task_mapping_allowed": False}},
    )
    task_records, edge_specs = classify_and_create_tasks([entity], {"github-api": entity.id})
    assert task_records == []
    assert edge_specs == {}


def test_filesystem_task_requires_access_evidence_not_filesystem_first_wording():
    weak = _entity("weak", description="Filesystem-first framework for durable backend services.")
    strong = _entity("strong", description="MCP server for filesystem access", entity_type="mcp")
    task_records, edge_specs = classify_and_create_tasks([weak, strong], {"weak": weak.id, "strong": strong.id})
    assert [record.name for record in task_records] == ["filesystem access"]
    assert weak.id not in edge_specs
    assert edge_specs[strong.id][0]["task_source_key"] == "task:filesystem access"
