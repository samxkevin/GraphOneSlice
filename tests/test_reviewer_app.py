from __future__ import annotations

from pathlib import Path

from reviewer_app import ArtifactStore, REVIEWER_ROUTES


ROOT = Path(__file__).resolve().parents[1]


def test_reviewer_declares_all_required_routes():
    assert REVIEWER_ROUTES == {
        "/",
        "/ai-orbit",
        "/graphone",
        "/entities",
        "/relationships",
        "/validation",
        "/mapping",
        "/feasibility",
        "/categories",
    }


def test_reviewer_reads_committed_artifacts_without_ingestion():
    summary = ArtifactStore(ROOT).summary()
    assert summary["served_from"] == "committed local data artifacts"
    assert summary["ingestion_performed"] is False
    assert summary["ai_orbit"]["entities"] == 254
    assert summary["ai_orbit"]["relationships"] == 134
    assert summary["ai_orbit"]["validation_status"] == "passed"
    assert summary["graphone"]["validation_status"] == "passed"
    assert summary["graphone"]["summary"]["startups"] == 1000
    assert summary["graphone"]["summary"]["products"] == 1000
    assert summary["graphone"]["summary"]["research_papers"] == 1000


def test_reviewer_api_payloads_are_artifact_backed():
    store = ArtifactStore(ROOT)
    assert len(store.api_payload("/api/entities")) == 254
    assert len(store.api_payload("/api/relationships")) == 134
    assert store.api_payload("/api/validation")["status"] == "passed"
    graphone = store.api_payload("/api/graphone")
    assert graphone["summary"]["entity_mapping_log"] == 3000 + graphone["summary"]["news"]
    categories = store.api_payload("/api/categories")
    assert "models" in categories
    assert len(categories["models"]) == 91
