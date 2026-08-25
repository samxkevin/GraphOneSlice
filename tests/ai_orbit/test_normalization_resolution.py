from datetime import datetime, timezone

from src.ai_orbit.models import RawEntityRecord
from src.ai_orbit.stages.cleaning import clean_records
from src.ai_orbit.stages.normalization import normalize_records
from src.ai_orbit.stages.resolution import resolve_entities
from src.ai_orbit.utils.identity import normalize_name
from src.ai_orbit.utils.url import normalize_url


def test_openai_name_variants_normalize_to_one_canonical_value():
    assert normalize_name("OpenAI") == "openai"
    assert normalize_name("Open AI") == "openai"
    assert normalize_name("OpenAI, Inc.") == "openai"


def test_url_normalization_collapses_equivalent_urls():
    assert normalize_url("HTTPS://GitHub.com/OpenAI/OpenAI-Python/?utm_source=x#readme") == "https://github.com/openai/openai-python"
    assert normalize_url("https://github.com/openai/openai-python") == "https://github.com/openai/openai-python"


def test_duplicate_source_records_resolve_to_single_entity():
    now = datetime.now(timezone.utc)
    records = [
        RawEntityRecord(
            source_key="test:1",
            entity_type="company",
            name="Open AI",
            description="Observed company record.",
            url="https://example.com/openai",
            categories=["Companies"],
            source_name="fixture",
            source_url="https://example.com/source/1",
            raw={},
            fetched_at=now,
        ),
        RawEntityRecord(
            source_key="test:2",
            entity_type="company",
            name="OpenAI, Inc.",
            description="Observed duplicate company record.",
            url="https://example.com/openai-inc",
            categories=["Companies"],
            source_name="fixture",
            source_url="https://example.com/source/2",
            raw={},
            fetched_at=now,
        ),
    ]
    candidates = normalize_records(clean_records(records))
    entities, mapping, source_to_id, _source_to_key, duplicates = resolve_entities(candidates)
    assert len(entities) == 1
    assert duplicates == 1
    assert entities[0].name == "OpenAI"
    assert len(mapping) == 2
    assert source_to_id["test:1"] == source_to_id["test:2"]
