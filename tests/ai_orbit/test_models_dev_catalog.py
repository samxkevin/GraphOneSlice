from datetime import datetime, timezone

from src.ai_orbit.adapters.models_dev_catalog import ModelsDevGitHubCatalogAdapter
from src.ai_orbit.config import AIOrbitSettings


def _valid_model_row():
    return {
        "id": "meta-llama/llama-4-maverick",
        "canonical_slug": "meta-llama/llama-4-maverick-17b-128e-instruct",
        "name": "Meta: Llama 4 Maverick",
        "description": "Llama 4 Maverick is a multimodal language model from Meta.",
        "created": 1743881822,
        "context_length": 1048576,
        "architecture": {
            "modality": "text+image->text",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "tokenizer": "Llama4",
        },
        "top_provider": {"max_completion_tokens": 16384},
        "supported_parameters": ["temperature", "top_p"],
        "knowledge_cutoff": "2024-08-31",
        "links": {"details": "/api/v1/models/meta-llama/llama-4-maverick-17b-128e-instruct/endpoints"},
    }


def test_models_dev_filter_requires_model_identity_modalities_and_details_url():
    adapter = ModelsDevGitHubCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))
    assert adapter._is_candidate_model(_valid_model_row())

    missing_modalities = _valid_model_row()
    missing_modalities["architecture"] = {"modality": "text->text", "input_modalities": [], "output_modalities": ["text"]}
    assert not adapter._is_candidate_model(missing_modalities)

    alias_row = _valid_model_row()
    alias_row["id"] = "~openai/gpt-latest"
    assert not adapter._is_candidate_model(alias_row)

    free_variant = _valid_model_row()
    free_variant["id"] = "meta-llama/llama-3.3-70b-instruct:free"
    assert not adapter._is_candidate_model(free_variant)

    duplicate_provider = _valid_model_row()
    duplicate_provider["id"] = "openai/gpt-5"
    assert not adapter._is_candidate_model(duplicate_provider)


def test_models_dev_record_preserves_source_backed_metadata_without_license_invention():
    adapter = ModelsDevGitHubCatalogAdapter(AIOrbitSettings(log_level="CRITICAL"))
    record = adapter._record_from_model(
        _valid_model_row(),
        source_url="https://api.github.com/repos/anomalyco/models.dev/contents/models.json?ref=dev",
        evidence_url="https://github.com/anomalyco/models.dev/blob/dev/models.json",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert record.entity_type == "model"
    assert record.categories == ["Models"]
    assert record.url == "https://models.dev/api/v1/models/meta-llama/llama-4-maverick-17b-128e-instruct/endpoints"
    model_metadata = record.metadata["model"]
    assert model_metadata["provider"] == "Meta"
    assert model_metadata["license"] is None
    assert model_metadata["modalities"] == "text+image->text"
    assert model_metadata["input_modalities"] == ["text", "image"]
    assert model_metadata["output_modalities"] == ["text"]
    assert model_metadata["source_created_at"] == "2025-04-05T19:37:02+00:00"
    assert model_metadata["source_evidence_url"] == "https://github.com/anomalyco/models.dev/blob/dev/models.json"
