from datetime import datetime, timezone

from src.ai_orbit.adapters.pyvideo_videos import (
    PyVideoVideosAdapter,
    _is_ai_relevant,
    _normalize_iso_date,
    _video_ai_tokens,
)
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import Entity, Provenance, SourceRef
from src.ai_orbit.stages.validation import validate_outputs


def _row(**overrides):
    row = {
        "title": "Building LLM Applications with Python",
        "description": "This talk demonstrates how to build large language model applications.",
        "recorded": "2024-05-19",
        "videos": [{"type": "youtube", "url": "https://www.youtube.com/watch?v=Mu4R7Zo8lkM"}],
        "speakers": ["Ada Lovelace"],
        "language": "eng",
        "related_urls": [{"label": "Conference Website", "url": "https://us.pycon.org/2024/"}],
        "thumbnail_url": "https://i.ytimg.com/vi/Mu4R7Zo8lkM/hqdefault.jpg",
        "_event": "pycon-us-2024",
        "_slug": "building-llm-applications-with-python",
        "_api_url": "https://api.github.com/repos/pyvideo/data/contents/pycon-us-2024/videos/building-llm-applications-with-python.json",
    }
    row.update(overrides)
    return row


def _adapter() -> PyVideoVideosAdapter:
    return PyVideoVideosAdapter(AIOrbitSettings(log_level="CRITICAL"))


def test_short_ai_tokens_use_word_boundaries():
    strong, weak = _video_ai_tokens("maintain a system")
    assert strong == []
    assert weak == []


def test_is_ai_relevant_requires_strong_or_two_weak_signals():
    assert _is_ai_relevant("large language model deployment")
    assert _is_ai_relevant("Building LLM Applications")
    # One weak signal alone is not enough.
    assert not _is_ai_relevant("gpu debugging")
    # Two weak signals are enough.
    assert _is_ai_relevant("gpu training for inference")


def test_normalize_iso_date_handles_date_only_and_rejects_garbage():
    assert _normalize_iso_date("2024-05-19") == "2024-05-19"
    assert _normalize_iso_date("2024-05-19T10:30:00+00:00") == "2024-05-19"
    assert _normalize_iso_date("not-a-date") is None
    assert _normalize_iso_date("") is None


def test_candidate_video_rejects_missing_identity_and_non_youtube_urls():
    adapter = _adapter()
    assert adapter._is_candidate_video(_row())

    assert not adapter._is_candidate_video(_row(title=""))
    assert not adapter._is_candidate_video(_row(videos=[{"type": "youtube", "url": "https://example.com/watch?v=123"}]))
    assert not adapter._is_candidate_video(_row(recorded=None))
    assert not adapter._is_candidate_video(_row(description=""))
    # Not AI-relevant.
    assert not adapter._is_candidate_video(_row(
        title="Web scraping with Python",
        description="A talk about HTTP clients and HTML parsing.",
        _slug="web-scraping-with-python",
    ))


def test_record_from_row_preserves_source_backed_video_fields():
    adapter = _adapter()
    record = adapter._record_from_row(
        _row(), event="pycon-us-2024", event_title="PyCon US 2024", fetched_at=datetime.now(timezone.utc)
    )
    assert record is not None
    assert record.entity_type == "video"
    assert record.categories == ["Videos"]
    assert record.url == "https://www.youtube.com/watch?v=Mu4R7Zo8lkM"
    assert record.source_url == "https://api.github.com/repos/pyvideo/data/contents/pycon-us-2024/videos/building-llm-applications-with-python.json"
    assert record.source_key == "pyvideo:video:pycon-us-2024:building-llm-applications-with-python"

    video = record.metadata["video"]
    assert video["canonical_url"] == "https://www.youtube.com/watch?v=Mu4R7Zo8lkM"
    assert video["youtube_video_id"] == "Mu4R7Zo8lkM"
    assert video["recorded_at"] == "2024-05-19"
    assert video["timestamp_semantics"] == "pyvideo_recorded_date"
    assert video["publisher"] == {"name": "PyCon US 2024", "event": "pycon-us-2024", "type": "conference"}
    assert video["speakers"] == ["Ada Lovelace"]
    assert video["language"] == "eng"
    assert video["ai_relevance_evidence"]["matched_tokens"]
    assert "large language model applications" in record.description


def test_slug_suggests_ai_uses_slug_tokens():
    adapter = _adapter()
    assert adapter._slug_suggests_ai("building-llm-applications-with-python.json")
    assert adapter._slug_suggests_ai("machine-learning-accelerators.json")
    assert not adapter._slug_suggests_ai("web-scraping-with-python.json")
    assert not adapter._slug_suggests_ai("notes.txt")


def test_video_validation_requires_identity_recorded_at_publisher_and_evidence():
    video = Entity(
        id="video-1",
        entity_type="video",
        name="Building LLM Applications with Python",
        description="This talk demonstrates how to build large language model applications.",
        url="https://www.youtube.com/watch?v=Mu4R7Zo8lkM",
        categories=["Videos"],
        source=SourceRef(name="fixture", url="https://example.com/source"),
        metadata={
            "video": {
                "canonical_url": "https://www.youtube.com/watch?v=Mu4R7Zo8lkM",
                "youtube_video_id": "Mu4R7Zo8lkM",
                "recorded_at": "2024-05-19",
                "timestamp_semantics": "pyvideo_recorded_date",
                "publisher": {"name": "PyCon US 2024", "event": "pycon-us-2024", "type": "conference"},
                "ai_relevance_evidence": {"matched_tokens": ["llm", "large language model"], "excerpt": "Building LLM Applications with Python"},
            },
        },
        provenance=Provenance(
            discovered_by="fixture",
            source_url="https://example.com/source",
            source_record_id="fixture:video",
            observed_fields={"name": "Building LLM Applications with Python"},
        ),
    )
    accepted, _relationships, report = validate_outputs([video], [])
    assert len(accepted) == 1
    assert report["status"] == "passed"

    missing_metadata = video.model_copy(update={"id": "video-2", "metadata": {}})
    accepted, _relationships, report = validate_outputs([missing_metadata], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_date = video.model_copy(update={"id": "video-3", "metadata": {"video": {**video.metadata["video"], "recorded_at": None}}})
    accepted, _relationships, report = validate_outputs([missing_date], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    bad_date = video.model_copy(update={"id": "video-4", "metadata": {"video": {**video.metadata["video"], "recorded_at": "sometime"}}})
    accepted, _relationships, report = validate_outputs([bad_date], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_publisher = video.model_copy(update={"id": "video-5", "metadata": {"video": {**video.metadata["video"], "publisher": {"name": ""}}}})
    accepted, _relationships, report = validate_outputs([missing_publisher], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1

    missing_evidence = video.model_copy(update={"id": "video-6", "metadata": {"video": {**video.metadata["video"], "ai_relevance_evidence": None}}})
    accepted, _relationships, report = validate_outputs([missing_evidence], [])
    assert accepted == []
    assert report["failure_counts_by_type"]["invalid_metadata"] == 1
