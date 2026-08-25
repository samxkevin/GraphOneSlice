from datetime import datetime, timezone

from src.ai_orbit.adapters.ai_tools_products import AIToolsProductDirectoryAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def test_ai_tools_product_filter_requires_product_identity_and_ai_description_evidence():
    adapter = AIToolsProductDirectoryAdapter(AIOrbitSettings(log_level="CRITICAL"))
    assert adapter._is_candidate_product(
        {
            "id": 1,
            "handle": "wonderchat",
            "website": "https://wonderchat.io",
            "description": "AI Chatbot builder to create custom ChatGPT chatbots from website links or PDFs.",
        }
    )
    assert not adapter._is_candidate_product(
        {
            "id": 2,
            "handle": "plain-directory-entry",
            "website": "https://example.com",
            "description": "Customer feedback dashboard for product teams.",
        }
    )
    assert not adapter._is_candidate_product(
        {
            "id": 3,
            "handle": "missing-url",
            "website": "",
            "description": "AI writing assistant.",
        }
    )


def test_ai_tools_product_record_preserves_source_identity_and_product_metadata():
    adapter = AIToolsProductDirectoryAdapter(AIOrbitSettings(log_level="CRITICAL"))
    record = adapter._record_from_row(
        {
            "id": 3,
            "handle": "wonderchat",
            "website": "https://wonderchat.io/",
            "description": "AI Chatbot builder to create custom ChatGPT chatbots from website links or PDFs.",
        },
        source_url="https://api.github.com/repos/lakey009/AI-Tools-List/contents/AIToolsList-Sample.json",
        evidence_url="https://github.com/lakey009/AI-Tools-List/blob/main/AIToolsList-Sample.json",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert record.entity_type == "product"
    assert record.categories == ["Products"]
    assert record.url == "https://wonderchat.io/"
    assert record.metadata["product"]["provider"] is None
    assert record.metadata["product"]["ai_relevance_evidence"]["field"] == "description"
    assert record.source_url == "https://api.github.com/repos/lakey009/AI-Tools-List/contents/AIToolsList-Sample.json"


def test_product_validation_requires_product_metadata_evidence():
    product = Entity(
        id="product-1",
        entity_type="product",
        name="Wonderchat",
        description="AI Chatbot builder to create custom ChatGPT chatbots from website links or PDFs.",
        url="https://wonderchat.io",
        categories=["Products"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata={"product": {"canonical_url": "https://wonderchat.io", "ai_relevance_evidence": {"field": "description"}}},
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:product",
            observed_fields={"name": "Wonderchat"},
        ),
    )
    accepted, _relationships, report = validate_outputs([product], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    missing_metadata = product.model_copy(update={"id": "product-2", "metadata": {}})
    accepted, _relationships, report = validate_outputs([missing_metadata], [])
    assert accepted == []
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1
