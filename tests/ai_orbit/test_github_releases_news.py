from datetime import datetime, timezone

from src.ai_orbit.adapters.github_releases_news import (
    GitHubReleasesNewsAdapter,
    _ai_signal_tokens,
    _normalize_iso_timestamp,
)
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def _release(**overrides):
    release = {
        "id": 12345,
        "tag_name": "v1.2.3",
        "name": "Release v1.2.3",
        "body": "This release adds [agent](https://example.com) tool-calling support.\n\n- feature one\n- feature two",
        "html_url": "https://github.com/openai/openai-python/releases/tag/v1.2.3",
        "url": "https://api.github.com/repos/openai/openai-python/releases/12345",
        "published_at": "2026-08-19T10:50:47Z",
        "created_at": "2026-08-19T10:00:00Z",
        "draft": False,
        "prerelease": False,
    }
    release.update(overrides)
    return release


def _repo(**overrides):
    repo = {
        "full_name": "openai/openai-python",
        "description": "The official Python library for the OpenAI API",
        "topics": ["openai", "python"],
        "owner": {"login": "openai", "type": "Organization", "html_url": "https://github.com/openai"},
    }
    repo.update(overrides)
    return repo


def _adapter() -> GitHubReleasesNewsAdapter:
    return GitHubReleasesNewsAdapter(AIOrbitSettings(log_level="CRITICAL"))


def test_ai_signal_tokens_use_word_boundaries_for_short_tokens():
    # "ai" inside "maintain" must not count as an AI signal.
    assert _ai_signal_tokens("maintain") == []
    assert "ai" in _ai_signal_tokens("AI platform for models")
    assert "openai" in _ai_signal_tokens("The official Python library for the OpenAI API")


def test_normalize_iso_timestamp_handles_z_and_rejects_garbage():
    assert _normalize_iso_timestamp("2026-08-19T10:50:47Z") == "2026-08-19T10:50:47+00:00"
    assert _normalize_iso_timestamp("2026-08-19T10:50:47+00:00") == "2026-08-19T10:50:47+00:00"
    assert _normalize_iso_timestamp("not-a-timestamp") is None
    assert _normalize_iso_timestamp("") is None


def test_release_candidate_rejects_draft_prerelease_and_missing_publication_time():
    adapter = _adapter()
    assert adapter._is_candidate_release(_release())

    assert not adapter._is_candidate_release(_release(draft=True))
    assert not adapter._is_candidate_release(_release(prerelease=True))
    assert not adapter._is_candidate_release(_release(published_at=None))
    assert not adapter._is_candidate_release(_release(body=""))
    assert not adapter._is_candidate_release(_release(html_url=""))


def test_record_from_release_preserves_source_backed_news_fields():
    adapter = _adapter()
    record = adapter._record_from_release(_release(), _repo(), fetched_at=datetime.now(timezone.utc))
    assert record is not None
    assert record.entity_type == "news"
    assert record.categories == ["News"]
    assert record.url == "https://github.com/openai/openai-python/releases/tag/v1.2.3"
    assert record.source_url == "https://api.github.com/repos/openai/openai-python/releases/12345"
    assert record.source_key == "github:release:openai/openai-python:12345"

    news = record.metadata["news"]
    assert news["canonical_url"] == "https://github.com/openai/openai-python/releases/tag/v1.2.3"
    assert news["published_at"] == "2026-08-19T10:50:47+00:00"
    assert news["timestamp_semantics"] == "github_release_published_at"
    assert news["tag_name"] == "v1.2.3"
    assert news["release_id"] == 12345
    assert news["publisher"]["login"] == "openai"
    assert news["publisher"]["type"] == "Organization"
    assert news["repository"] == "openai/openai-python"
    assert news["ai_relevance_evidence"]["matched_tokens"] == ["openai"]

    # The release body is used as the description and link text is preserved.
    assert "agent tool-calling support" in record.description


def test_record_emits_published_by_relationship_only_for_organization_owners():
    adapter = _adapter()

    org_record = adapter._record_from_release(_release(), _repo(), fetched_at=datetime.now(timezone.utc))
    assert org_record is not None
    assert any(
        rel["relationship_type"] == "published_by" and rel["other_source_key"] == "github:org:openai"
        for rel in org_record.pending_relationships
    )

    user_repo = _repo(owner={"login": "some-user", "type": "User", "html_url": "https://github.com/some-user"})
    user_record = adapter._record_from_release(_release(), user_repo, fetched_at=datetime.now(timezone.utc))
    assert user_record is not None
    assert user_record.pending_relationships == []
    assert user_record.metadata["news"]["publisher"]["login"] == "some-user"


def test_ai_relevance_evidence_requires_observed_signal():
    adapter = _adapter()
    assert adapter._ai_relevance_evidence(_repo()) is not None
    empty_repo = _repo(description="", topics=[], full_name="some-user/unrelated-repo")
    assert adapter._ai_relevance_evidence(empty_repo) is None


def test_news_validation_requires_published_at_semantics_and_evidence():
    news = Entity(
        id="news-1",
        entity_type="news",
        name="Release v1.2.3",
        description="This release adds agent tool-calling support.",
        url="https://github.com/openai/openai-python/releases/tag/v1.2.3",
        categories=["News"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata={
            "news": {
                "canonical_url": "https://github.com/openai/openai-python/releases/tag/v1.2.3",
                "published_at": "2026-08-19T10:50:47+00:00",
                "timestamp_semantics": "github_release_published_at",
                "publisher": {"login": "openai", "type": "Organization", "html_url": "https://github.com/openai"},
                "ai_relevance_evidence": {"matched_tokens": ["openai"], "excerpt": "The official Python library for the OpenAI API"},
            },
        },
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:news",
            observed_fields={"name": "Release v1.2.3"},
        ),
    )
    accepted, _relationships, report = validate_outputs([news], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    missing_metadata = news.model_copy(update={"id": "news-2", "metadata": {}})
    accepted, _relationships, report = validate_outputs([missing_metadata], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_timestamp = news.model_copy(update={"id": "news-3", "metadata": {"news": {**news.metadata["news"], "published_at": None}}})
    accepted, _relationships, report = validate_outputs([missing_timestamp], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    fabricated_timestamp = news.model_copy(update={"id": "news-4", "metadata": {"news": {**news.metadata["news"], "published_at": "sometime"}}})
    accepted, _relationships, report = validate_outputs([fabricated_timestamp], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1
