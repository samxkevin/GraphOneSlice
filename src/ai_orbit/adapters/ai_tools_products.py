from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import is_valid_http_url, normalize_url


AI_PRODUCT_TERMS = {
    "ai",
    "chatgpt",
    "gpt",
    "llm",
    "machine learning",
    "generative",
    "stable diffusion",
}


class AIToolsProductDirectoryAdapter(SourceAdapter):
    """Ingests a bounded sample from a source-backed AI product directory.

    The source is a GitHub-hosted JSON directory of AI-powered tools, services,
    and platforms. Records are accepted only when the directory supplies product
    identity fields directly: handle, website, and description. The adapter does
    not visit product websites or infer providers that the directory does not
    name.
    """

    name = "AI Tools List Product Directory"

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
            usable_rows = [row for row in rows if self._is_candidate_product(row)]
            self._cache = rows
            self._response_url = response_url
            self._html_url = html_url
            status = "usable" if usable_rows else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON + curated directory file",
                access_method="GitHub REST contents API for a JSON AI tools/product directory sample",
                url=response_url,
                status=status,  # type: ignore[arg-type]
                domain="Products",
                http_status=200,
                pagination="sample JSON file is not paginated; full JSON file exists but is too large for GitHub contents base64 and raw.githubusercontent.com failed in this environment",
                available_fields=fields,
                required_fields=["id", "handle", "website", "description"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="directory entries do not provide product launch or publication time; no freshness timestamp is exported for products",
                anti_bot_js="GitHub REST API returned JSON file content; no browser automation or JavaScript required",
                inventory_evidence=f"sample JSON rows={len(rows)}; candidate rows with required fields and explicit AI description evidence={len(usable_rows)}",
                company_identity_quality="directory records identify product/tool handles and websites; provider/company is not reliably supplied and remains null",
                ai_relevance="source describes itself as an AI-powered tools/services/platforms directory; records are still filtered for explicit AI terms in the product description",
                actual_crawl_feasibility="usable for bounded Product records from the sample JSON file; not treated as authoritative provider/company metadata",
                record_volume_estimate=f"bounded by AI_ORBIT_AI_TOOLS_PRODUCT_LIMIT={self.settings.ai_tools_product_limit}; sample inventory={len(rows)}",
                failure_behavior="403/404/malformed JSON are source failures; 429/5xx use bounded retry via the shared HTTP client",
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON + curated directory file",
                access_method="GitHub REST contents API for a JSON AI tools/product directory sample",
                url=self.settings.ai_tools_product_directory_api_url,
                status="unusable",
                domain="Products",
                http_status=exc.status_code,
                required_fields=["id", "handle", "website", "description"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._cache:
            await self.verify()
        source_url = self._response_url or self.settings.ai_tools_product_directory_api_url
        evidence_url = self._html_url or source_url
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_urls: set[str] = set()
        for row in self._cache:
            if len(records) >= self.settings.ai_tools_product_limit:
                break
            record = self._record_from_row(row, source_url=source_url, evidence_url=evidence_url, fetched_at=now)
            if record is None:
                continue
            if record.url in seen_urls:
                continue
            seen_urls.add(record.url)
            records.append(record)
        return records

    async def _fetch_rows(self) -> tuple[list[dict[str, Any]], str, str | None, list[str]]:
        response = await self.client.get_json(self.settings.ai_tools_product_directory_api_url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "unexpected GitHub contents payload for AI tools product directory")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "missing base64 content for AI tools product directory sample")
        try:
            text = base64.b64decode(content).decode("utf-8", "replace")
            parsed = json.loads(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "malformed AI tools product directory JSON") from exc
        if not isinstance(parsed, list):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "AI tools product directory JSON is not an array")
        rows = [row for row in parsed if isinstance(row, dict)]
        fields = sorted({key for row in rows[:25] for key in row.keys()})
        return rows, response.url, data.get("html_url") if isinstance(data.get("html_url"), str) else None, fields

    def _record_from_row(self, row: dict[str, Any], *, source_url: str, evidence_url: str, fetched_at: datetime) -> RawEntityRecord | None:
        if not self._is_candidate_product(row):
            return None
        handle = str(row["handle"]).strip()
        website = normalize_url(str(row["website"]))
        description = re.sub(r"\s+", " ", str(row["description"]).strip())
        directory_id = row.get("id")
        evidence = self._ai_relevance_evidence(description)
        return RawEntityRecord(
            source_key=f"ai-tools-list:product:{directory_id}:{handle.lower()}",
            entity_type="product",
            name=handle,
            description=description,
            url=website,
            categories=["Products"],
            source_name=self.name,
            source_url=source_url,
            raw={"directory_id": directory_id, "handle": handle, "website": row.get("website"), "description": row.get("description")},
            metadata={
                "product": {
                    "directory_id": directory_id,
                    "directory_handle": handle,
                    "canonical_url": website,
                    "provider": None,
                    "ai_relevance_evidence": evidence,
                    "source_evidence_url": evidence_url,
                }
            },
            fetched_at=fetched_at,
        )

    def _is_candidate_product(self, row: dict[str, Any]) -> bool:
        handle = row.get("handle")
        website = row.get("website")
        description = row.get("description")
        if not isinstance(handle, str) or not handle.strip():
            return False
        if not isinstance(website, str) or not is_valid_http_url(normalize_url(website)):
            return False
        if not isinstance(description, str) or not description.strip():
            return False
        return self._ai_relevance_evidence(description) is not None

    def _ai_relevance_evidence(self, description: str) -> dict[str, Any] | None:
        normalized = f" {re.sub(r'[^a-z0-9]+', ' ', description.lower()).strip()} "
        signals = sorted(term for term in AI_PRODUCT_TERMS if f" {term} " in normalized)
        # GPT-4/GPT4 style identifiers are common product evidence but are not
        # matched by the whitespace phrase logic above.
        if re.search(r"\bgpt[- ]?\d", description, flags=re.I):
            signals.append("gpt identifier")
        if not signals:
            return None
        return {"field": "description", "signals": sorted(set(signals)), "excerpt": description[:240]}
