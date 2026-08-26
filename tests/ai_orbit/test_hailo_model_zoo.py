from datetime import datetime, timezone

from src.ai_orbit.adapters.hailo_model_zoo import (
    HailoModelZooAdapter,
    _canonical_device_url,
    _device_name_for_arch,
    _parse_model_yaml,
)
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.stages.normalization import normalize_records
from src.ai_orbit.stages.relationships import map_relationships
from src.ai_orbit.stages.resolution import resolve_entities
from src.ai_orbit.stages.validation import validate_outputs
from src.ai_orbit.utils.url import normalize_url


def _adapter() -> HailoModelZooAdapter:
    return HailoModelZooAdapter(AIOrbitSettings(log_level="CRITICAL"))


_YOLO_YAML = """\
base:
- base/yolov8.yaml
network:
  network_name: hailo_yolov8m_384_640
paths:
  network_path:
  - models_files/HailoNets/VPU/hailo_object_detection/yolov8m/2025-11-09/hailo_yolov8m_384_640.onnx
  url: https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ObjectDetection/yolov8m.zip
info:
  task: object detection
  input_shape: 384x640x3
  operations: 47.2G
  parameters: 3.0M
  source: https://github.com/ultralytics/ultralytics
  license_name: AGPL-3.0
  supported_hw_arch:
  - hailo15h
  - hailo15l
  - hailo10h
"""

_NO_ARCH_YAML = """\
base:
- base/arcface.yaml
network:
  network_name: arcface_mobilefacenet
info:
  task: face recognition
  operations: 0.88G
"""

_NO_NETWORK_YAML = """\
info:
  supported_hw_arch:
  - hailo15h
"""

_MALFORMED_YAML = "base:\n- base/x.yaml\nnetwork:\n  network_name: [unclosed\n"


def test_parse_model_yaml_extracts_identity_and_compatibility():
    parsed = _parse_model_yaml(_YOLO_YAML)
    assert parsed is not None
    assert parsed["network_name"] == "hailo_yolov8m_384_640"
    assert parsed["supported_hw_arch"] == ["hailo15h", "hailo15l", "hailo10h"]
    assert parsed["task"] == "object detection"
    assert parsed["input_shape"] == "384x640x3"
    assert parsed["operations"] == "47.2G"
    assert parsed["parameters"] == "3.0M"
    assert parsed["source"] == "https://github.com/ultralytics/ultralytics"
    assert parsed["license_name"] == "AGPL-3.0"
    assert parsed["url"].startswith("https://hailo-model-zoo.s3")


def test_parse_model_yaml_requires_supported_hw_arch():
    assert _parse_model_yaml(_NO_ARCH_YAML) is None


def test_parse_model_yaml_requires_network_name():
    assert _parse_model_yaml(_NO_NETWORK_YAML) is None


def test_parse_model_yaml_handles_malformed_yaml():
    assert _parse_model_yaml(_MALFORMED_YAML) is None


def test_arch_to_device_name_is_source_backed():
    assert _device_name_for_arch("hailo15h") == "Hailo-15H"
    assert _device_name_for_arch("hailo15l") == "Hailo-15L"
    assert _device_name_for_arch("hailo10h") == "Hailo-10H"
    assert _device_name_for_arch("hailo8") is None  # not on master branch


def test_device_canonical_urls_are_distinct_per_arch():
    urls = {arch: _canonical_device_url(arch) for arch in ("hailo15h", "hailo15l", "hailo10h")}
    assert len(set(urls.values())) == 3
    assert all(url.startswith("https://github.com/hailo-ai/hailo_model_zoo/tree/master/docs/public_models/") for url in urls.values())
    assert "HAILO15H" in urls["hailo15h"]
    assert "HAILO15L" in urls["hailo15l"]
    assert "HAILO10H" in urls["hailo10h"]


def test_sample_paths_is_deterministic_and_bounded():
    adapter = _adapter()
    paths = [f"hailo_model_zoo/cfg/networks/model_{i}.yaml" for i in range(233)]
    first = adapter._sample_paths(paths)
    second = adapter._sample_paths(paths)
    assert first == second
    assert len(first) == adapter.settings.hailo_model_limit


def test_model_record_uses_artifact_url_and_hailo_provider():
    adapter = _adapter()
    parsed = _parse_model_yaml(_YOLO_YAML)
    parsed["_path"] = "hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"
    record = adapter._model_record(parsed, fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert record is not None
    assert record.entity_type == "model"
    assert record.name == "hailo_yolov8m_384_640"
    assert record.url.startswith("https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/")
    assert record.metadata["model"]["provider"] == "Hailo"
    assert record.metadata["model"]["model_identifier"] == "hailo_yolov8m_384_640"
    assert record.metadata["model"]["supported_hw_arch"] == ["hailo15h", "hailo15l", "hailo10h"]
    assert record.metadata["model"]["source_repository"] == "https://github.com/ultralytics/ultralytics"
    assert record.pending_relationships == []  # models never declare relationships themselves


def test_model_record_falls_back_to_blob_url_without_artifact():
    adapter = _adapter()
    parsed = _parse_model_yaml(_YOLO_YAML)
    parsed["url"] = None
    parsed["_path"] = "hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"
    record = adapter._model_record(parsed, fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert record is not None
    assert record.url == "https://github.com/hailo-ai/hailo_model_zoo/blob/master/hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"


def test_device_record_declares_runs_edges_for_each_supported_model():
    adapter = _adapter()
    model = _parse_model_yaml(_YOLO_YAML)
    record = adapter._device_record("hailo15h", [model], fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert record is not None
    assert record.entity_type == "device"
    assert record.name == "Hailo-15H"
    assert record.metadata["device"]["manufacturer"] == "Hailo"
    assert record.metadata["device"]["device_class"] == "ai-accelerator"
    assert record.metadata["device"]["canonical_url"] == normalize_url(_canonical_device_url("hailo15h"))
    assert record.metadata["device"]["ai_relevance_evidence"]
    assert len(record.pending_relationships) == 1
    edge = record.pending_relationships[0]
    assert edge["relationship_type"] == "runs"
    assert edge["other_source_key"] == "hailo-model-zoo:model:hailo_yolov8m_384_640"
    assert edge["evidence"]["observed_field"] == "info.supported_hw_arch"
    assert "hailo15h" in edge["evidence"]["observed_value"]


def test_runs_edges_resolve_device_as_source_and_model_as_target():
    adapter = _adapter()
    parsed = _parse_model_yaml(_YOLO_YAML)
    parsed["_path"] = "hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    model_record = adapter._model_record(parsed, fetched_at=now)
    device_records = [adapter._device_record(arch, [parsed], fetched_at=now) for arch in parsed["supported_hw_arch"]]
    raw_records = [model_record, *device_records]

    candidates = normalize_records(raw_records)
    entities, _mapping, source_key_to_id, _canonical, _dups = resolve_entities(candidates)
    relationships = map_relationships(raw_records, entities, source_key_to_id, {})

    device_ids = {e.name: e.id for e in entities if e.entity_type == "device"}
    model_ids = {e.name: e.id for e in entities if e.entity_type == "model"}
    runs = [r for r in relationships if r.relationship_type == "runs"]
    assert len(runs) == 3  # one edge per declared arch
    for rel in runs:
        assert rel.source_entity_id in device_ids.values()
        assert rel.target_entity_id == model_ids["hailo_yolov8m_384_640"]
        assert rel.evidence["observed_field"] == "info.supported_hw_arch"
        assert rel.evidence["source_url"] == "https://github.com/hailo-ai/hailo_model_zoo/blob/master/hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"
        assert rel.method == "source_supported_hw_arch"


def test_hailo_records_pass_validation():
    adapter = _adapter()
    parsed = _parse_model_yaml(_YOLO_YAML)
    parsed["_path"] = "hailo_model_zoo/cfg/networks/hailo_yolov8m_384_640.yaml"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    raw_records = [adapter._model_record(parsed, fetched_at=now)]
    raw_records += [adapter._device_record(arch, [parsed], fetched_at=now) for arch in parsed["supported_hw_arch"]]
    candidates = normalize_records(raw_records)
    entities, _mapping, source_key_to_id, _canonical, _dups = resolve_entities(candidates)
    relationships = map_relationships(raw_records, entities, source_key_to_id, {})
    valid_entities, valid_relationships, report = validate_outputs(entities, relationships)
    assert report["status"] == "passed"
    assert len(valid_entities) == 4  # 1 model + 3 devices
    assert len(valid_relationships) == 3
