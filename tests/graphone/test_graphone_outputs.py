from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from src.graphone.build import (
    GraphOneBuildError,
    SourceFetchFailure,
    _product_rejection_reason,
    _stable_id,
    build_graphone_outputs,
    validate_graphone_records,
)


ROOT = Path(__file__).resolve().parents[2]


def _mapping(record_type: str, record: dict[str, object]) -> dict[str, object]:
    return {
        "record_type": record_type,
        "raw_source_key": f"fixture:{record_type}:{record['id']}",
        "raw_value": str(record["id"]),
        "canonical_id": record["id"],
        "canonical_value": str(record["id"]),
        "method": "fixture",
        "confidence": 1.0,
        "source_url": record["source_url"],
        "reason": "fixture",
    }


def _valid_records(now: datetime) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    timestamp = now.isoformat()
    startup = {
        "id": "startup-id",
        "canonical_name": "Example Startup",
        "employee_count": 7,
        "source_url": "https://example.test/startup",
        "collectedAt": timestamp,
        "provenance": {"source": "fixture"},
    }
    product = {
        "id": "product-id",
        "product_name": "Example Product",
        "product_url": "https://example.test/product",
        "description": "A source-backed AI product.",
        "source_url": "https://example.test/products-source",
        "collectedAt": timestamp,
        "provenance": {"ai_relevance_evidence": {"field": "description"}},
    }
    paper = {
        "id": "paper-id",
        "recordType": "RESEARCH_PAPER",
        "paper_url": "https://arxiv.org/abs/2601.00001",
        "published_date": timestamp,
        "source_url": "https://arxiv.org/abs/2601.00001",
        "collectedAt": timestamp,
        "provenance": {"source": "fixture"},
    }
    news = {
        "id": "news-id",
        "title": "Release 1.0",
        "canonical_url": "https://github.com/example/project/releases/tag/v1",
        "publisher": "example",
        "published_at": timestamp,
        "timestamp_semantics": "github_release_published_at",
        "source_url": "https://api.github.com/repos/example/project/releases/1",
        "collectedAt": timestamp,
        "provenance": {"ai_relevance_evidence": {"matched_tokens": ["ai"]}},
    }
    mappings = [
        _mapping("startup", startup),
        _mapping("product", product),
        _mapping("research_paper", paper),
        _mapping("news", news),
    ]
    return [startup], [product], [paper], [], [news], mappings


def test_product_gate_requires_direct_identity_product_semantics_and_ai_evidence():
    assert _product_rejection_reason({"id": 1, "handle": "guide", "website": "https://example.test", "description": "A guide to AI"}) == "non_product_semantics"
    assert _product_rejection_reason({"id": 1, "handle": "not-ai", "website": "https://example.test", "description": "A scheduling platform."}) == "missing_explicit_ai_evidence"
    assert _product_rejection_reason({"id": 1, "handle": "tool", "website": "https://example.test", "description": "An AI writing product."}) is None


def test_stable_ids_are_deterministic_and_record_type_scoped():
    assert _stable_id("startup", "fixture:1") == _stable_id("startup", "fixture:1")
    assert _stable_id("startup", "fixture:1") != _stable_id("product", "fixture:1")


def test_graphone_validator_rejects_non_fresh_or_semantically_invalid_news():
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    startups, products, papers, jobs, news, mappings = _valid_records(now)
    news[0]["published_at"] = (now - timedelta(hours=25)).isoformat()
    news[0]["timestamp_semantics"] = "crawl_time"
    report = validate_graphone_records(
        startups=startups,
        products=products,
        research_papers=papers,
        jobs=jobs,
        news=news,
        mappings=mappings,
        generated_at=now,
        freshness_window_start=now - timedelta(hours=24),
    )
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["news_outside_freshness_window"] == 1
    assert report["failure_counts_by_type"]["invalid_news_timestamp_semantics"] == 1


def test_graphone_validator_requires_mapping_for_each_accepted_record():
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    startups, products, papers, jobs, news, mappings = _valid_records(now)
    report = validate_graphone_records(
        startups=startups,
        products=products,
        research_papers=papers,
        jobs=jobs,
        news=news,
        mappings=mappings[:-1],
        generated_at=now,
        freshness_window_start=now - timedelta(hours=24),
    )
    assert report["status"] == "failed"
    assert report["failure_counts_by_type"]["mapping_coverage_failure"] == 1


def test_required_source_failure_preserves_existing_output_directory(tmp_path: Path):
    class FailingFetcher:
        def get_blob_text(self, _repository: str, _blob_sha: str) -> str:
            raise SourceFetchFailure("fixture source unavailable")

    output = tmp_path / "graphone"
    output.mkdir()
    marker = output / "last-verified.json"
    marker.write_text('{"keep": true}\n', encoding="utf-8")
    with pytest.raises(GraphOneBuildError):
        build_graphone_outputs(output, fetcher=FailingFetcher())
    assert marker.read_text(encoding="utf-8") == '{"keep": true}\n'


def test_committed_graphone_artifacts_are_complete_and_validation_passes():
    root = ROOT / "data" / "graphone"
    report = json.loads((root / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["failures"] == []
    summary = report["summary"]
    assert summary["startups"] == 1000
    assert summary["products"] == 1000
    assert summary["research_papers"] == 1000
    assert summary["jobs"] == 0
    assert summary["news"] >= 0
    assert summary["entity_mapping_log"] == 3000 + summary["news"]
    assert summary["total_records"] == 3000 + summary["news"]
    assert summary["mapping_coverage"] == 1.0
    assert summary["provenance_coverage"] == 1.0
    assert datetime.fromisoformat(summary["freshness_window_start"])
    assert datetime.fromisoformat(summary["freshness_window_end"])
    expected_counts = {
        "startups": summary["startups"],
        "products": summary["products"],
        "research_papers": summary["research_papers"],
        "jobs": summary["jobs"],
        "news": summary["news"],
    }
    for name, expected in expected_counts.items():
        payload = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
        records = payload["records"]
        assert len(records) == expected
        assert len({record["id"] for record in records}) == expected
        assert all(record.get("provenance") for record in records)
        assert all(record.get("source_url", "").startswith(("https://", "http://")) for record in records)
    assert len(json.loads((root / "entity_mapping_log.json").read_text(encoding="utf-8"))) == summary["entity_mapping_log"]
