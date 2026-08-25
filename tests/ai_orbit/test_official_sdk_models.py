from src.ai_orbit.adapters.official_sdk_models import OfficialSDKModelAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.utils.url import normalize_url


def test_official_sdk_model_parser_extracts_literals_with_line_numbers():
    adapter = OfficialSDKModelAdapter(AIOrbitSettings(log_level="CRITICAL"))
    text = 'Model = Literal[\n    "alpha",\n    "beta",\n]\n'
    observed = adapter._parse_model_identifiers(text)
    assert [item.identifier for item in observed] == ["alpha", "beta"]
    assert [item.line_number for item in observed] == [2, 3]


def test_github_line_anchor_is_preserved_for_source_evidence_url():
    assert normalize_url("https://github.com/OpenAI/openai-python/blob/main/src/openai/types/shared/chat_model.py#L52") == (
        "https://github.com/openai/openai-python/blob/main/src/openai/types/shared/chat_model.py#L52"
    )
    assert normalize_url("https://github.com/OpenAI/openai-python#readme") == "https://github.com/openai/openai-python"
