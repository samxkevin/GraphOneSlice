"""Regression tests for the Qualcomm AI Hub model catalog adapter.

These encode the source's quality gate: model identity and license metadata are
taken verbatim from the manifest, the deterministic stride sample stays bounded,
and no license/modality/provider/device relationship is invented.
"""

from datetime import datetime, timezone

import pytest

from src.ai_orbit.adapters.qualcomm_ai_hub import (
    QualcommAIHubAdapter,
    _parse_manifest_yaml,
    _provider_from_source_repo,
)
from src.ai_orbit.config import AIOrbitSettings


_MANIFEST_YAML = """\
id: yolov8_det
name: YOLOv8-Detection
description: Ultralytics YOLOv8 is a machine learning model that predicts bounding boxes and classes of objects in an image.
domain: Computer Vision
use_case: Object Detection
license: https://github.com/ultralytics/ultralytics/blob/main/LICENSE
license_type: agpl-3.0
source_repo: https://github.com/ultralytics/ultralytics/tree/main/ultralytics/models/yolo/detect
research_paper: https://docs.ultralytics.com/tasks/detect/
research_paper_title: 'Ultralytics YOLOv8 Docs: Object Detection'
status: published
supported_precisions:
- float
- w8a16
tags:
- real-time
"""

_NO_DESCRIPTION = """\
id: broken
name: Broken
status: published
"""

_MALFORMED = "id: [unclosed\n"

_NOT_PUBLISHED = """\
id: preview_model
name: Preview Model
description: A preview model not yet published.
status: preview
"""


def _adapter() -> QualcommAIHubAdapter:
    return QualcommAIHubAdapter(AIOrbitSettings(log_level="CRITICAL"))


def test_parse_manifest_extracts_identity_fields():
    parsed = _parse_manifest_yaml(_MANIFEST_YAML)
    assert parsed is not None
    assert parsed["id"] == "yolov8_det"
    assert parsed["name"] == "YOLOv8-Detection"
    assert parsed["license_type"] == "agpl-3.0"
    assert parsed["domain"] == "Computer Vision"


def test_parse_manifest_requires_description():
    assert _parse_manifest_yaml(_NO_DESCRIPTION) is None


def test_parse_manifest_rejects_malformed_yaml():
    assert _parse_manifest_yaml(_MALFORMED) is None


def test_provider_from_source_repo_derives_github_slug():
    assert _provider_from_source_repo("https://github.com/ultralytics/ultralytics/tree/main") == "ultralytics"
    assert _provider_from_source_repo("https://github.com/google-research/bert") == "google-research"
    assert _provider_from_source_repo("https://huggingface.co/Qwen/Qwen3.5-0.8B") == "Qwen"
    assert _provider_from_source_repo("https://arxiv.org/abs/1810.04805") is None
    assert _provider_from_source_repo(None) is None


def test_model_record_preserves_license_and_source_metadata_without_invention():
    adapter = _adapter()
    record = adapter._model_record(
        _parse_manifest_yaml(_MANIFEST_YAML),
        path="src/qai_hub_models/models/yolov8_det/manifest.yaml",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert record.entity_type == "model"
    assert record.categories == ["Models"]
    assert record.name == "YOLOv8-Detection"
    assert record.url == "https://github.com/qualcomm/ai-hub-models/blob/main/src/qai_hub_models/models/yolov8_det/manifest.yaml"
    model = record.metadata["model"]
    assert model["license"] == "agpl-3.0"
    assert model["license_url"] == "https://github.com/ultralytics/ultralytics/blob/main/LICENSE"
    assert model["modalities"] is None
    assert model["provider"] == "ultralytics"
    assert model["domain"] == "Computer Vision"
    assert model["use_case"] == "Object Detection"
    assert model["source_repository"].startswith("https://github.com/ultralytics")


def test_model_record_falls_back_to_qualcomm_provider_without_source_repo():
    adapter = _adapter()
    manifest = _parse_manifest_yaml(
        "id: facemap_3dmm\n"
        "name: Facial-Landmark-Detection\n"
        "description: This model's architecture was developed by Qualcomm.\n"
        "domain: Computer Vision\n"
        "status: published\n"
        "license_type: bsd-3-clause\n"
    )
    record = adapter._model_record(
        manifest,
        path="src/qai_hub_models/models/facemap_3dmm/manifest.yaml",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert record.metadata["model"]["provider"] == "Qualcomm"


def test_model_record_skips_non_published_status():
    adapter = _adapter()
    record = adapter._model_record(
        _parse_manifest_yaml(_NOT_PUBLISHED),
        path="src/qai_hub_models/models/preview_model/manifest.yaml",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is None


def test_sample_paths_is_deterministic_bounded_stride():
    adapter = QualcommAIHubAdapter(AIOrbitSettings(log_level="CRITICAL", qualcomm_ai_hub_model_limit=5))
    paths = [f"src/qai_hub_models/models/model_{i:03d}/manifest.yaml" for i in range(20)]
    sample = adapter._sample_paths(paths)
    assert len(sample) <= 5
    assert sample == adapter._sample_paths(paths)  # deterministic


@pytest.mark.asyncio
async def test_discover_is_bounded_unique_and_deterministic(monkeypatch):
    settings = AIOrbitSettings(log_level="CRITICAL", qualcomm_ai_hub_model_limit=4)
    adapter = QualcommAIHubAdapter(settings)
    paths = [f"src/qai_hub_models/models/model_{i:03d}/manifest.yaml" for i in range(10)]
    adapter._manifest_paths = paths

    async def fake_fetch(path: str) -> str:
        model_id = path.split("/")[-2]
        return (
            f"id: {model_id}\n"
            f"name: Model {model_id}\n"
            "description: A source-backed model description.\n"
            "domain: Computer Vision\n"
            "status: published\n"
            "license_type: apache-2.0\n"
        )

    monkeypatch.setattr(adapter, "_fetch_yaml_text", fake_fetch)
    records = await adapter.discover()
    assert len(records) <= 4
    ids = [r.metadata["model"]["model_identifier"] for r in records]
    assert len(ids) == len(set(ids))  # unique
    records2 = await adapter.discover()
    assert [r.metadata["model"]["model_identifier"] for r in records2] == ids  # deterministic
