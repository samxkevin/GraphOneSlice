from __future__ import annotations

import base64
from datetime import datetime, timezone
import math
from typing import Any

import yaml

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url

# Source-derived device identity. The official Hailo Model Zoo README names the
# three device families on the master branch as "Hailo-15H", "Hailo-15L", and
# "Hailo-10H", and documents them under docs/public_models/<DEVICE_DIR>/. The
# lowercase arch codes below are exactly the values the model YAMLs declare in
# ``info.supported_hw_arch``; the product name is the README's own spelling of
# that code, and the docs directory is the source's per-device catalog page.
_ARCH_INFO: dict[str, dict[str, str]] = {
    "hailo15h": {
        "name": "Hailo-15H",
        "docs_dir": "HAILO15H",
        "evidence": "README.rst: 'For Hailo-15H - ...' and docs/public_models/HAILO15H/",
    },
    "hailo15l": {
        "name": "Hailo-15L",
        "docs_dir": "HAILO15L",
        "evidence": "README.rst: 'For Hailo-15L - ...' and docs/public_models/HAILO15L/",
    },
    "hailo10h": {
        "name": "Hailo-10H",
        "docs_dir": "HAILO10H",
        "evidence": "README.rst: 'For Hailo-10H - ...' and docs/public_models/HAILO10H/",
    },
}

_NETWORKS_PATH_PREFIX = "hailo_model_zoo/cfg/networks/"

_REPO_DESCRIPTION = "The Hailo Model Zoo includes pre-trained models and a full building and evaluation environment"


def _canonical_device_url(arch: str) -> str | None:
    info = _ARCH_INFO.get(arch)
    if not info:
        return None
    return f"https://github.com/hailo-ai/hailo_model_zoo/tree/master/docs/public_models/{info['docs_dir']}"


def _device_name_for_arch(arch: str) -> str | None:
    info = _ARCH_INFO.get(arch)
    return info["name"] if info else None


def _parse_model_yaml(text: str) -> dict[str, Any] | None:
    """Parse one Hailo model zoo network YAML into the fields we need.

    Returns a dict with ``network_name``, ``supported_hw_arch`` (list of arch
    codes), and optional ``task``, ``input_shape``, ``operations``,
    ``parameters``, ``source`` (original model source), ``license_name``, and
    ``url`` (pre-trained artifact). Returns ``None`` when the YAML does not
    establish model identity plus explicit hardware compatibility, or when it
    cannot be parsed at all.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    network = data.get("network")
    if not isinstance(network, dict):
        return None
    network_name = network.get("network_name")
    if not isinstance(network_name, str) or not network_name.strip():
        return None
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    supported = info.get("supported_hw_arch")
    if not isinstance(supported, list) or not supported:
        return None
    supported = [str(arch).strip().lower() for arch in supported if isinstance(arch, str) and arch.strip()]
    if not supported:
        return None
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    url = paths.get("url")
    return {
        "network_name": network_name.strip(),
        "supported_hw_arch": supported,
        "task": info.get("task") if isinstance(info.get("task"), str) else None,
        "input_shape": info.get("input_shape") if isinstance(info.get("input_shape"), str) else None,
        "operations": info.get("operations") if isinstance(info.get("operations"), str) else None,
        "parameters": info.get("parameters") if isinstance(info.get("parameters"), str) else None,
        "source": info.get("source") if isinstance(info.get("source"), str) else None,
        "license_name": info.get("license_name") if isinstance(info.get("license_name"), str) else None,
        "url": url if isinstance(url, str) and url.strip() else None,
    }


class HailoModelZooAdapter(SourceAdapter):
    """Ingests Device -> runs -> Model relationships from the Hailo model zoo.

    The official hailo-ai/hailo_model_zoo repository holds one YAML definition
    per supported model under ``hailo_model_zoo/cfg/networks/``. Each YAML
    declares ``network.network_name`` (model identity) and an explicit
    ``info.supported_hw_arch`` list (the Hailo AI accelerators that run it).
    This is direct source evidence for ``Device -> runs -> Model``: the edge is
    created only when a model's own YAML names the device, never inferred from
    framework support or popularity.

    The adapter ingests a bounded deterministic sample of model definitions and
    the three device families the sample declares (Hailo-15H/15L/10H). Models
    whose YAML lacks ``supported_hw_arch`` are excluded because they supply no
    compatibility evidence. No relationship is fabricated when the field is
    absent.
    """

    name = "Hailo Model Zoo"

    def __init__(self, settings: AIOrbitSettings):
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GraphOneSlice-AIOrbit-VerticalSlice/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = JsonHttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            verify=settings.ca_bundle,
            headers=headers,
            retry=HttpRetryConfig(
                max_attempts=settings.max_retry_attempts,
                backoff_base_seconds=settings.retry_backoff_base_seconds,
                backoff_max_seconds=settings.retry_backoff_max_seconds,
                jitter_seconds=settings.retry_jitter_seconds,
            ),
        )
        self._network_paths: list[str] | None = None
        self._inventory: dict[str, Any] = {}

    async def verify(self) -> SourceFeasibility:
        url = self.settings.hailo_model_zoo_tree_url
        try:
            paths = await self._fetch_network_paths()
            self._network_paths = paths
            sample_paths = sorted(paths)[:3]
            sample_parsed = 0
            for path in sample_paths:
                text = await self._fetch_yaml_text(path)
                if _parse_model_yaml(text) is not None:
                    sample_parsed += 1
            status = "usable" if sample_parsed else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured YAML hardware/model compatibility catalog",
                access_method="GitHub REST git-trees API (recursive enumeration) + contents API for hailo-ai/hailo_model_zoo cfg/networks/*.yaml",
                url=url,
                status=status,  # type: ignore[arg-type]
                domain="Devices",
                http_status=200,
                pagination="single repository tree; adapter ingests a bounded deterministic stride sample of model definitions",
                available_fields=[
                    "network.network_name",
                    "info.supported_hw_arch",
                    "info.task",
                    "info.input_shape",
                    "info.operations",
                    "info.parameters",
                    "info.source",
                    "info.license_name",
                    "paths.url",
                ],
                required_fields=["network.network_name", "info.supported_hw_arch"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="the source does not supply per-device timestamps; no release/publication date is fabricated for devices or models",
                anti_bot_js="GitHub REST API returned YAML as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=self._inventory_evidence(paths),
                company_identity_quality="device identity is source-derived: the official README names Hailo-15H/15L/10H and documents each under docs/public_models/<DEVICE>/; manufacturer is the repository owner (Hailo)",
                ai_relevance="the catalog is Hailo's official zoo of AI models compiled for Hailo AI accelerators; every edge is backed by info.supported_hw_arch",
                actual_crawl_feasibility="usable for Device and Model records plus Device -> runs -> Model edges with explicit per-model hardware support",
                record_volume_estimate=f"bounded by AI_ORBIT_HAILO_MODEL_LIMIT={self.settings.hailo_model_limit} sampled from the {len(paths)} network YAMLs",
                failure_behavior="403/404/malformed tree or YAML are source failures; a single unparseable model YAML is skipped without failing the source",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured YAML hardware/model compatibility catalog",
                access_method="GitHub REST git-trees + contents API for hailo-ai/hailo_model_zoo",
                url=url,
                status="unusable",
                domain="Devices",
                http_status=exc.status_code,
                required_fields=["network.network_name", "info.supported_hw_arch"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if self._network_paths is None:
            self._network_paths = await self._fetch_network_paths()
        now = datetime.now(timezone.utc)
        parsed_models: list[dict[str, Any]] = []
        for path in self._sample_paths(self._network_paths):
            if len(parsed_models) >= self.settings.hailo_model_limit:
                break
            text = await self._fetch_yaml_text(path)
            parsed = _parse_model_yaml(text)
            if parsed is None:
                # Per-record isolation: a model YAML without supported_hw_arch,
                # or that cannot be parsed, is skipped rather than failing the
                # whole source.
                continue
            parsed["_path"] = path
            parsed_models.append(parsed)

        model_records: list[RawEntityRecord] = []
        arch_to_models: dict[str, list[dict[str, Any]]] = {}
        for parsed in parsed_models:
            record = self._model_record(parsed, fetched_at=now)
            if record is None:
                continue
            model_records.append(record)
            for arch in parsed["supported_hw_arch"]:
                arch_to_models.setdefault(arch, []).append(parsed)

        records: list[RawEntityRecord] = []
        records.extend(model_records)
        for arch, models in sorted(arch_to_models.items()):
            device_record = self._device_record(arch, models, fetched_at=now)
            if device_record is not None:
                records.append(device_record)
        return records

    def _sample_paths(self, paths: list[str]) -> list[str]:
        """Deterministic bounded stride sample over the sorted catalog.

        A stride (rather than the alphabetically first N) spreads the sample
        across the catalog's task families (classification, detection,
        segmentation, face, NLP, ...) instead of concentrating on whichever
        family sorts first. The stride is computed from the full inventory and
        the configured limit so the sample is reproducible for a given tree.
        """
        ordered = sorted(paths)
        if len(ordered) <= self.settings.hailo_model_limit:
            return ordered
        stride = math.ceil(len(ordered) / self.settings.hailo_model_limit)
        return ordered[::stride]

    def _blob_url(self, path: str) -> str:
        return f"https://github.com/hailo-ai/hailo_model_zoo/blob/master/{path}"

    def _contents_url(self, path: str) -> str:
        return f"{self.settings.hailo_model_zoo_contents_base}{path}"

    def _model_record(self, parsed: dict[str, Any], *, fetched_at: datetime) -> RawEntityRecord | None:
        network_name = parsed["network_name"]
        path = parsed.get("_path") or ""
        artifact_url = parsed.get("url")
        blob_url = self._blob_url(path) if path else None
        url = artifact_url or blob_url
        if not url or not is_valid_http_url(url):
            return None
        parts = [network_name]
        if parsed.get("task"):
            parts.append(f"task: {parsed['task']}")
        if parsed.get("input_shape"):
            parts.append(f"input shape: {parsed['input_shape']}")
        if parsed.get("operations"):
            parts.append(f"operations: {parsed['operations']}")
        if parsed.get("parameters"):
            parts.append(f"parameters: {parsed['parameters']}")
        description = "Hailo Model Zoo network " + "; ".join(parts)
        source_url = self._contents_url(path) if path else self.settings.hailo_model_zoo_tree_url
        return RawEntityRecord(
            source_key=f"hailo-model-zoo:model:{network_name}",
            entity_type="model",
            name=network_name,
            description=description,
            url=normalize_url(url),
            categories=["Models"],
            source_name=self.name,
            source_url=normalize_url(source_url),
            raw={
                "network_name": network_name,
                "path": path,
                "supported_hw_arch": parsed["supported_hw_arch"],
                "task": parsed.get("task"),
                "input_shape": parsed.get("input_shape"),
                "operations": parsed.get("operations"),
                "parameters": parsed.get("parameters"),
                "source": parsed.get("source"),
                "license_name": parsed.get("license_name"),
                "artifact_url": artifact_url,
            },
            metadata={
                "model": {
                    "model_identifier": network_name,
                    "provider": "Hailo",
                    "supported_hw_arch": parsed["supported_hw_arch"],
                    "task": parsed.get("task"),
                    "input_shape": parsed.get("input_shape"),
                    "operations": parsed.get("operations"),
                    "parameters": parsed.get("parameters"),
                    "license": parsed.get("license_name"),
                    "modalities": None,
                    "source_repository": parsed.get("source"),
                }
            },
            fetched_at=fetched_at,
        )

    def _device_record(self, arch: str, models: list[dict[str, Any]], *, fetched_at: datetime) -> RawEntityRecord | None:
        name = _device_name_for_arch(arch)
        url = _canonical_device_url(arch)
        if not name or not url:
            return None
        pending_relationships: list[dict[str, Any]] = []
        for model in models:
            model_path = model.get("_path") or ""
            pending_relationships.append(
                {
                    "relationship_type": "runs",
                    "other_source_key": f"hailo-model-zoo:model:{model['network_name']}",
                    "method": "source_supported_hw_arch",
                    "evidence": {
                        "observed_field": "info.supported_hw_arch",
                        "observed_value": model["supported_hw_arch"],
                        "source_url": normalize_url(self._blob_url(model_path)) if model_path else normalize_url(self.settings.hailo_model_zoo_tree_url),
                        "reason": (
                            f"model '{model['network_name']}' YAML declares '{arch}' in "
                            "info.supported_hw_arch"
                        ),
                    },
                }
            )
        return RawEntityRecord(
            source_key=f"hailo-model-zoo:device:{arch}",
            entity_type="device",
            name=name,
            description=(
                f"{name} AI accelerator; declared as supported hardware by "
                f"{len(models)} sampled Hailo Model Zoo model definitions."
            ),
            url=normalize_url(url),
            categories=["Devices"],
            source_name=self.name,
            source_url=normalize_url(self.settings.hailo_model_zoo_tree_url),
            raw={
                "arch_code": arch,
                "product_name": name,
                "docs_dir": _ARCH_INFO[arch]["docs_dir"],
            },
            metadata={
                "device": {
                    "canonical_url": normalize_url(url),
                    "device_class": "ai-accelerator",
                    "manufacturer": "Hailo",
                    "manufacturer_evidence": (
                        "source repository is the official hailo-ai/hailo_model_zoo "
                        f"repository; {_ARCH_INFO[arch]['evidence']}"
                    ),
                    "ai_relevance_evidence": {
                        "matched_tokens": ["hailo", "accelerator"],
                        "excerpt": (
                            f"{_REPO_DESCRIPTION}; '{arch}' is declared in "
                            f"info.supported_hw_arch by {len(models)} sampled model YAMLs"
                        ),
                    },
                }
            },
            pending_relationships=pending_relationships,
            fetched_at=fetched_at,
        )

    async def _fetch_network_paths(self) -> list[str]:
        response = await self.client.get_json(
            self.settings.hailo_model_zoo_tree_url,
            params={"recursive": "1"},
        )
        data = response.data
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "Hailo model zoo tree payload missing 'tree' array")
        paths: list[str] = []
        for item in data["tree"]:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if (
                isinstance(path, str)
                and item.get("type") == "blob"
                and path.startswith(_NETWORKS_PATH_PREFIX)
                and path.endswith(".yaml")
            ):
                paths.append(path)
        if not paths:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "Hailo model zoo tree contained no network YAMLs")
        return sorted(paths)

    async def _fetch_yaml_text(self, path: str) -> str:
        url = f"{self.settings.hailo_model_zoo_contents_base}{path}"
        response = await self.client.get_json(url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Hailo model zoo contents payload for {path} was not an object")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Hailo model zoo YAML {path} missing base64 content")
        try:
            return base64.b64decode(content).decode("utf-8", "replace")
        except ValueError as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Hailo model zoo YAML {path} had malformed base64 content") from exc

    def _inventory_evidence(self, paths: list[str]) -> str:
        return (
            f"network YAMLs in catalog={len(paths)}; "
            f"bounded sample limit={self.settings.hailo_model_limit}; "
            f"device families documented in source={len(_ARCH_INFO)} (Hailo-15H/15L/10H)"
        )
