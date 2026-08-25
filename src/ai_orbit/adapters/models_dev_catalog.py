from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import quote

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url


_EXCLUDED_PROVIDER_PREFIXES = {"openai", "anthropic"}


class ModelsDevGitHubCatalogAdapter(SourceAdapter):
    """Ingests bounded model metadata from the Models.dev GitHub catalog.

    The direct models.dev API probe fails in this environment, but the same
    open-source catalog is reachable through GitHub REST contents. This adapter
    uses only source-supplied model facts and keeps license null because the
    catalog does not expose a license field per model.
    """

    name = "Models.dev GitHub Model Catalog"

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
        self._cache: list[dict[str, Any]] = []
        self._response_url: str | None = None
        self._html_url: str | None = None

    async def verify(self) -> SourceFeasibility:
        try:
            rows, response_url, html_url, fields = await self._fetch_rows()
            usable_rows = [row for row in rows if self._is_candidate_model(row)]
            self._cache = rows
            self._response_url = response_url
            self._html_url = html_url
            status = "usable" if usable_rows else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON + open-source model metadata catalog",
                access_method="GitHub REST contents API for anomalyco/models.dev models.json",
                url=response_url,
                status=status,  # type: ignore[arg-type]
                domain="Models",
                http_status=200,
                pagination="single generated JSON catalog; adapter uses a bounded deterministic sample rather than full ingestion",
                available_fields=fields,
                required_fields=[
                    "id",
                    "name",
                    "description",
                    "architecture.modality",
                    "architecture.input_modalities",
                    "architecture.output_modalities",
                    "links.details",
                ],
                authentication_required=False,
                rate_limit_observed={},
                freshness="records include a source 'created' epoch and optional knowledge_cutoff, but neither is treated as an independently verified model release date",
                anti_bot_js="GitHub REST API returned JSON file content; no browser automation or JavaScript required",
                inventory_evidence=(
                    f"models.json rows={len(rows)}; candidate rows after required fields, alias/free-variant filtering, "
                    f"and OpenAI/Anthropic duplicate-avoidance={len(usable_rows)}"
                ),
                company_identity_quality="provider identity is source-supplied through model IDs and names; no company metadata is inferred",
                ai_relevance="Models.dev describes itself as an open-source database of AI model specifications, pricing, and capabilities",
                actual_crawl_feasibility="usable for bounded Model records with source-supplied modality/capability metadata",
                record_volume_estimate=f"bounded by AI_ORBIT_MODELS_DEV_MODEL_LIMIT={self.settings.models_dev_model_limit}; catalog inventory={len(rows)}",
                failure_behavior="403/404/malformed JSON are source failures; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON + open-source model metadata catalog",
                access_method="GitHub REST contents API for anomalyco/models.dev models.json",
                url=self.settings.models_dev_github_catalog_api_url,
                status="unusable",
                domain="Models",
                http_status=exc.status_code,
                required_fields=["id", "name", "description", "architecture", "links.details"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._cache:
            await self.verify()
        source_url = self._response_url or self.settings.models_dev_github_catalog_api_url
        evidence_url = self._html_url or source_url
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_model_ids: set[str] = set()
        for row in self._cache:
            if len(records) >= self.settings.models_dev_model_limit:
                break
            record = self._record_from_model(row, source_url=source_url, evidence_url=evidence_url, fetched_at=now)
            if record is None:
                continue
            model_id = record.metadata["model"]["model_identifier"]
            if model_id in seen_model_ids:
                continue
            seen_model_ids.add(model_id)
            records.append(record)
        return records

    async def _fetch_rows(self) -> tuple[list[dict[str, Any]], str, str | None, list[str]]:
        response = await self.client.get_json(self.settings.models_dev_github_catalog_api_url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "unexpected GitHub contents payload for Models.dev catalog")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "missing base64 content for Models.dev models.json")
        try:
            text = base64.b64decode(content).decode("utf-8", "replace")
            parsed = json.loads(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "malformed Models.dev models.json") from exc
        rows = parsed.get("data") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "Models.dev models.json missing data array")
        model_rows = [row for row in rows if isinstance(row, dict)]
        fields = sorted({key for row in model_rows[:25] for key in row.keys()})
        return model_rows, response.url, data.get("html_url") if isinstance(data.get("html_url"), str) else None, fields

    def _record_from_model(
        self,
        row: dict[str, Any],
        *,
        source_url: str,
        evidence_url: str,
        fetched_at: datetime,
    ) -> RawEntityRecord | None:
        if not self._is_candidate_model(row):
            return None
        model_id = str(row["id"]).strip()
        architecture = row["architecture"]
        links = row["links"]
        details_url = self._details_url(str(links["details"]))
        provider = self._provider_name(row)
        source_created_unix = row.get("created") if isinstance(row.get("created"), int) else None
        source_created_at = (
            datetime.fromtimestamp(source_created_unix, tz=timezone.utc).isoformat() if source_created_unix is not None else None
        )
        supported_parameters = row.get("supported_parameters") if isinstance(row.get("supported_parameters"), list) else []
        top_provider = row.get("top_provider") if isinstance(row.get("top_provider"), dict) else {}
        return RawEntityRecord(
            source_key=f"models-dev:model:{model_id}",
            entity_type="model",
            name=str(row["name"]).strip(),
            description=" ".join(str(row["description"]).split()),
            url=details_url,
            categories=["Models"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "id": model_id,
                "canonical_slug": row.get("canonical_slug"),
                "name": row.get("name"),
                "description": row.get("description"),
                "architecture": architecture,
                "context_length": row.get("context_length"),
                "supported_parameters": supported_parameters,
                "knowledge_cutoff": row.get("knowledge_cutoff"),
                "created": source_created_unix,
                "links": links,
            },
            metadata={
                "model": {
                    "model_identifier": model_id,
                    "canonical_slug": row.get("canonical_slug"),
                    "provider": provider,
                    "license": None,
                    "modalities": architecture.get("modality"),
                    "input_modalities": architecture.get("input_modalities"),
                    "output_modalities": architecture.get("output_modalities"),
                    "context_length": row.get("context_length"),
                    "max_completion_tokens": top_provider.get("max_completion_tokens"),
                    "supported_parameters": supported_parameters,
                    "knowledge_cutoff": row.get("knowledge_cutoff"),
                    "source_created_unix": source_created_unix,
                    "source_created_at": source_created_at,
                    "source_evidence_url": evidence_url,
                }
            },
            fetched_at=fetched_at,
        )

    def _is_candidate_model(self, row: dict[str, Any]) -> bool:
        model_id = row.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            return False
        model_id = model_id.strip()
        if model_id.startswith("~") or model_id.endswith(":free"):
            return False
        provider_prefix = model_id.split("/", 1)[0]
        if provider_prefix in _EXCLUDED_PROVIDER_PREFIXES:
            return False
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            return False
        if not isinstance(row.get("description"), str) or not row["description"].strip():
            return False
        architecture = row.get("architecture")
        if not isinstance(architecture, dict):
            return False
        if not isinstance(architecture.get("modality"), str) or not architecture["modality"].strip():
            return False
        if not isinstance(architecture.get("input_modalities"), list) or not architecture["input_modalities"]:
            return False
        if not isinstance(architecture.get("output_modalities"), list) or not architecture["output_modalities"]:
            return False
        links = row.get("links")
        if not isinstance(links, dict) or not isinstance(links.get("details"), str):
            return False
        return is_valid_http_url(self._details_url(links["details"]))

    def _details_url(self, details_path: str) -> str:
        if details_path.startswith("http://") or details_path.startswith("https://"):
            return details_path
        return "https://models.dev" + quote(details_path if details_path.startswith("/") else f"/{details_path}", safe="/:?=&%")

    def _provider_name(self, row: dict[str, Any]) -> str:
        name = str(row.get("name") or "").strip()
        if ":" in name:
            provider = name.split(":", 1)[0].strip()
            if provider:
                return provider
        model_id = str(row.get("id") or "").strip()
        provider = model_id.split("/", 1)[0]
        return provider.replace("-", " ").title()
