"""Qualcomm AI Hub Models adapter (Models).

The official qualcomm/ai-hub-models repository is Qualcomm's catalog of machine
learning models optimized for Qualcomm devices. Each model lives under
``src/qai_hub_models/models/<model>/`` with a ``manifest.yaml`` carrying
website-facing metadata: ``id``, ``name``, ``description``, ``domain``,
``use_case``, ``license`` / ``license_type``, ``source_repo``,
``research_paper`` / ``research_paper_title``, ``technical_details``,
``supported_precisions``, and ``tags``.

This adapter ingests a bounded deterministic stride sample of model manifests.
It intentionally does NOT emit Device entities or Device -> runs -> Model edges:
the catalog's ``devices_and_chipsets.yaml`` lists Qualcomm chipsets/devices, but
the per-model manifests declare no explicit supported-device list, so no
compatibility edge can be evidenced from the source and none is fabricated.

Every field exported (including license) is taken directly from the manifest;
no license/modality/provider/timestamp is invented.
"""

from __future__ import annotations

import base64
import math
import re
from datetime import datetime, timezone
from typing import Any

import yaml

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url

_MANIFEST_PATH_PREFIX = "src/qai_hub_models/models/"
_REPO_BLOB_BASE = "https://github.com/qualcomm/ai-hub-models/blob/main/"


def _parse_manifest_yaml(text: str) -> dict[str, Any] | None:
    """Parse one Qualcomm AI Hub model manifest into its fields.

    Returns ``None`` when the YAML is malformed or lacks the core identity
    fields (``id``, ``name``, ``description``).
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("id", "name", "description"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
    return data


def _provider_from_source_repo(source_repo: str | None) -> str | None:
    """Derive the upstream provider slug from a source_repo URL.

    E.g. ``https://github.com/ultralytics/ultralytics`` -> ``ultralytics`` and
    ``https://huggingface.co/Qwen/Qwen3.5-0.8B`` -> ``Qwen``. Returns ``None``
    when the source repository is not a GitHub/Hugging Face URL, so no provider
    is invented for other upstreams.
    """
    if not isinstance(source_repo, str):
        return None
    for pattern in (r"https?://github\.com/([^/]+)/", r"https?://huggingface\.co/([^/]+)/"):
        match = re.match(pattern, source_repo.strip())
        if match:
            return match.group(1)
    return None


class QualcommAIHubAdapter(SourceAdapter):
    """Ingests bounded Model records from the Qualcomm AI Hub model catalog."""

    name = "Qualcomm AI Hub Models"

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
        self._manifest_paths: list[str] | None = None

    async def verify(self) -> SourceFeasibility:
        url = self.settings.qualcomm_ai_hub_tree_url
        try:
            paths = await self._fetch_manifest_paths()
            self._manifest_paths = paths
            sample_parsed = 0
            for path in sorted(paths)[:3]:
                text = await self._fetch_yaml_text(path)
                if _parse_manifest_yaml(text) is not None:
                    sample_parsed += 1
            status = "usable" if sample_parsed else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured YAML model metadata catalog",
                access_method="GitHub REST git-trees API (recursive enumeration) + contents API for qualcomm/ai-hub-models model manifests",
                url=url,
                status=status,  # type: ignore[arg-type]
                domain="Models",
                http_status=200,
                pagination="single repository tree; adapter ingests a bounded deterministic stride sample of model manifests",
                available_fields=[
                    "id",
                    "name",
                    "description",
                    "domain",
                    "use_case",
                    "license",
                    "license_type",
                    "source_repo",
                    "research_paper",
                    "research_paper_title",
                    "technical_details",
                    "supported_precisions",
                    "tags",
                    "status",
                ],
                required_fields=["id", "name", "description"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="the catalog does not supply per-model release timestamps; no release/publication date is fabricated for models",
                anti_bot_js="GitHub REST API returned YAML as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=(
                    f"model manifests in catalog={len(paths)}; bounded sample limit={self.settings.qualcomm_ai_hub_model_limit}"
                ),
                company_identity_quality="provider is derived from the manifest source_repo GitHub owner when present and recorded as a slug; no company entity is fabricated",
                ai_relevance="the catalog is Qualcomm's official collection of models optimized for Qualcomm AI devices; each model manifest supplies license, domain, use_case, and research-paper metadata",
                actual_crawl_feasibility="usable for bounded Model records with source-supplied license/domain/use_case metadata; no Device -> runs -> Model edges are emitted because manifests declare no per-model device support",
                record_volume_estimate=f"bounded by AI_ORBIT_QUALCOMM_AI_HUB_MODEL_LIMIT={self.settings.qualcomm_ai_hub_model_limit} sampled from the {len(paths)} model manifests",
                failure_behavior="403/404/malformed tree or YAML are source failures; a single unparseable manifest is skipped without failing the source",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted structured YAML model metadata catalog",
                access_method="GitHub REST git-trees + contents API for qualcomm/ai-hub-models model manifests",
                url=url,
                status="unusable",
                domain="Models",
                http_status=exc.status_code,
                required_fields=["id", "name", "description"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if self._manifest_paths is None:
            self._manifest_paths = await self._fetch_manifest_paths()
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_ids: set[str] = set()
        for path in self._sample_paths(self._manifest_paths):
            if len(records) >= self.settings.qualcomm_ai_hub_model_limit:
                break
            text = await self._fetch_yaml_text(path)
            parsed = _parse_manifest_yaml(text)
            if parsed is None:
                # Per-record isolation: an unparseable or incomplete manifest is
                # skipped rather than failing the whole source.
                continue
            record = self._model_record(parsed, path=path, fetched_at=now)
            if record is None:
                continue
            model_id = record.metadata["model"]["model_identifier"]
            if model_id in seen_ids:
                continue
            seen_ids.add(model_id)
            records.append(record)
        return records

    def _sample_paths(self, paths: list[str]) -> list[str]:
        """Deterministic bounded stride sample over the sorted manifest list.

        A stride spreads the sample across the catalog's model families
        (vision, LLM, audio, generative) instead of concentrating on whichever
        directory sorts first.
        """
        ordered = sorted(paths)
        if len(ordered) <= self.settings.qualcomm_ai_hub_model_limit:
            return ordered
        stride = math.ceil(len(ordered) / self.settings.qualcomm_ai_hub_model_limit)
        return ordered[::stride]

    def _blob_url(self, path: str) -> str:
        return f"{_REPO_BLOB_BASE}{path}"

    def _contents_url(self, path: str) -> str:
        return f"{self.settings.qualcomm_ai_hub_contents_base}{path}"

    def _model_record(self, parsed: dict[str, Any], *, path: str, fetched_at: datetime) -> RawEntityRecord | None:
        status = parsed.get("status")
        if isinstance(status, str) and status.strip() and status.strip() != "published":
            return None
        model_id = str(parsed["id"]).strip()
        name = str(parsed["name"]).strip()
        description = " ".join(str(parsed["description"]).split())
        blob_url = self._blob_url(path)
        source_repo = parsed.get("source_repo")
        license_url = parsed.get("license")
        license_type = parsed.get("license_type")
        # The provider is the upstream model maker when the manifest links a
        # GitHub/Hugging Face source repository; otherwise the catalog publisher
        # (Qualcomm) is the provider, since every manifest is published by the
        # official qualcomm/ai-hub-models repository.
        provider = _provider_from_source_repo(source_repo) or "Qualcomm"
        metadata: dict[str, Any] = {
            "model": {
                "model_identifier": model_id,
                "provider": provider,
                "license": license_type if isinstance(license_type, str) else None,
                "license_url": license_url if isinstance(license_url, str) else None,
                "modalities": None,
                "domain": parsed.get("domain") if isinstance(parsed.get("domain"), str) else None,
                "use_case": parsed.get("use_case") if isinstance(parsed.get("use_case"), str) else None,
                "source_repository": source_repo if isinstance(source_repo, str) else None,
                "research_paper": parsed.get("research_paper") if isinstance(parsed.get("research_paper"), str) else None,
                "research_paper_title": parsed.get("research_paper_title") if isinstance(parsed.get("research_paper_title"), str) else None,
                "technical_details": parsed.get("technical_details") if isinstance(parsed.get("technical_details"), dict) else None,
                "supported_precisions": parsed.get("supported_precisions") if isinstance(parsed.get("supported_precisions"), list) else [],
                "tags": parsed.get("tags") if isinstance(parsed.get("tags"), list) else [],
                "status": status if isinstance(status, str) else None,
                "source_evidence_url": blob_url,
            }
        }
        return RawEntityRecord(
            source_key=f"qualcomm-ai-hub:model:{model_id}",
            entity_type="model",
            name=name,
            description=description,
            url=normalize_url(blob_url),
            categories=["Models"],
            source_name=self.name,
            source_url=normalize_url(self._contents_url(path)),
            raw={
                "model_id": model_id,
                "path": path,
                "name": name,
                "domain": parsed.get("domain"),
                "use_case": parsed.get("use_case"),
                "license": license_type,
                "license_url": license_url,
                "source_repo": source_repo,
                "research_paper": parsed.get("research_paper"),
                "status": status,
                "supported_precisions": parsed.get("supported_precisions"),
                "tags": parsed.get("tags"),
            },
            metadata=metadata,
            fetched_at=fetched_at,
        )

    async def _fetch_manifest_paths(self) -> list[str]:
        response = await self.client.get_json(
            self.settings.qualcomm_ai_hub_tree_url,
            params={"recursive": "1"},
        )
        data = response.data
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "Qualcomm AI Hub tree payload missing 'tree' array")
        paths: list[str] = []
        for item in data["tree"]:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if (
                isinstance(path, str)
                and item.get("type") == "blob"
                and path.startswith(_MANIFEST_PATH_PREFIX)
                and path.endswith("/manifest.yaml")
                and "/_shared/" not in path
            ):
                parts = path.split("/")
                if len(parts) == 5 and not parts[3].startswith("_"):
                    paths.append(path)
        if not paths:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "Qualcomm AI Hub tree contained no model manifests")
        return sorted(paths)

    async def _fetch_yaml_text(self, path: str) -> str:
        url = self._contents_url(path)
        response = await self.client.get_json(url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Qualcomm AI Hub contents payload for {path} was not an object")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Qualcomm AI Hub manifest {path} missing base64 content")
        try:
            return base64.b64decode(content).decode("utf-8", "replace")
        except ValueError as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"Qualcomm AI Hub manifest {path} had malformed base64 content") from exc
