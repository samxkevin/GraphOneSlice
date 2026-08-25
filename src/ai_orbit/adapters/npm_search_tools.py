from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url


AI_RELEVANCE_TERMS = {
    "ai",
    "llm",
    "genai",
    "openai",
    "anthropic",
    "claude",
    "chatgpt",
    "gemini",
    "gpt",
    "agent",
    "agentic",
    "mcp",
    "model-context-protocol",
    "stable-diffusion",
    "comfyui",
    "generative",
}

CREATIVE_TERMS = {
    "stable-diffusion",
    "comfyui",
    "image",
    "video",
    "audio",
    "creative",
}

MCP_TERMS = {"mcp", "model-context-protocol", "model context protocol"}


class NpmSearchToolAdapter(SourceAdapter):
    """Ingests a bounded, source-backed sample of AI-related NPM tools.

    NPM search is not treated as a product catalog. Accepted records are package
    / tool entities only, and each accepted search hit is verified against its
    package-specific registry document before becoming a final record.
    """

    name = "NPM Search AI Tool Packages"

    def __init__(self, settings: AIOrbitSettings):
        self.settings = settings
        self.client = JsonHttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            verify=settings.ca_bundle,
            headers={"User-Agent": "GraphOneSlice-AIOrbit-VerticalSlice/0.1"},
            retry=HttpRetryConfig(
                max_attempts=settings.max_retry_attempts,
                backoff_base_seconds=settings.retry_backoff_base_seconds,
                backoff_max_seconds=settings.retry_backoff_max_seconds,
                jitter_seconds=settings.retry_jitter_seconds,
            ),
        )

    async def verify(self) -> SourceFeasibility:
        query = self.settings.npm_search_tool_queries[0]
        try:
            response = await self.client.get_json(
                "https://registry.npmjs.org/-/v1/search",
                params={"text": query, "size": 1},
            )
            objects = response.data.get("objects", []) if isinstance(response.data, dict) else []
            sample = objects[0].get("package", {}) if objects else {}
            status = "usable" if sample.get("name") and sample.get("description") and sample.get("links", {}).get("npm") else "partial"
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="NPM registry search endpoint plus package-specific registry documents",
                url=response.url,
                status=status,  # type: ignore[arg-type]
                domain="Tools/MCP/Creative",
                http_status=response.status_code,
                pagination="search endpoint supports size/from; this adapter uses bounded configured query sizes",
                available_fields=list(sample.keys())[:40],
                required_fields=["package.name", "package.description", "package.links.npm", "package.version", "package.date"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="package date/update fields are package version timestamps, not product launch or news publication times",
                anti_bot_js="NPM registry JSON endpoint returned JSON; no browser automation or JavaScript required",
                inventory_evidence=f"sample query {query!r} returned {len(objects)} object(s); total={response.data.get('total') if isinstance(response.data, dict) else None}",
                company_identity_quality="package publisher/maintainer fields do not reliably establish company identity; no company records are created from this source",
                ai_relevance="records are accepted only when package name/description/keywords contain explicit AI terms",
                actual_crawl_feasibility="usable for bounded tool/package sampling; not treated as a product catalog",
                record_volume_estimate=f"configured max records={self.settings.npm_search_tool_max_records}",
                failure_behavior="429/5xx retryable; malformed JSON rejected; individual package-document failures are skipped",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="NPM registry search endpoint plus package-specific registry documents",
                url="https://registry.npmjs.org/-/v1/search",
                status="unusable",
                domain="Tools/MCP/Creative",
                http_status=exc.status_code,
                required_fields=["package.name", "package.description", "package.links.npm", "package.version", "package.date"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        seen_packages: set[str] = set()
        for query in self.settings.npm_search_tool_queries:
            if len(records) >= self.settings.npm_search_tool_max_records:
                break
            response = await self.client.get_json(
                "https://registry.npmjs.org/-/v1/search",
                params={"text": query, "size": self.settings.npm_search_tool_limit_per_query},
            )
            for obj in response.data.get("objects", []) if isinstance(response.data, dict) else []:
                package = obj.get("package", {})
                name = package.get("name")
                if not isinstance(name, str) or name.lower() in seen_packages:
                    continue
                if not self._is_candidate_package(package):
                    continue
                try:
                    package_response = await self.client.get_json(self._registry_url(name))
                except SourceFetchError:
                    continue
                record = self._record_from_package(
                    search_object=obj,
                    package_doc=package_response.data,
                    source_url=package_response.url,
                    query=query,
                    fetched_at=now,
                )
                if record is None:
                    continue
                records.append(record)
                seen_packages.add(name.lower())
                if len(records) >= self.settings.npm_search_tool_max_records:
                    break
        return records

    def _is_candidate_package(self, package: dict[str, Any]) -> bool:
        name = package.get("name")
        description = package.get("description")
        npm_url = (package.get("links") or {}).get("npm")
        if not isinstance(name, str) or not isinstance(description, str) or not isinstance(npm_url, str):
            return False
        haystack = self._package_haystack(package)
        return any(term in haystack for term in AI_RELEVANCE_TERMS)

    def _record_from_package(
        self,
        *,
        search_object: dict[str, Any],
        package_doc: dict[str, Any],
        source_url: str,
        query: str,
        fetched_at: datetime,
    ) -> RawEntityRecord | None:
        search_package = search_object.get("package", {})
        latest = (package_doc.get("dist-tags") or {}).get("latest")
        version_doc = (package_doc.get("versions") or {}).get(latest, {}) if latest else {}
        name = version_doc.get("name") or package_doc.get("name") or search_package.get("name")
        description = (version_doc.get("description") or package_doc.get("description") or search_package.get("description") or "").strip()
        if not isinstance(name, str) or not description:
            return None
        if version_doc.get("deprecated"):
            return None
        npm_url = ((search_package.get("links") or {}).get("npm")) or f"https://www.npmjs.com/package/{name}"
        keywords = version_doc.get("keywords") or search_package.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        package_for_filter = {"name": name, "description": description, "keywords": keywords, "links": {"npm": npm_url}}
        if not self._is_candidate_package(package_for_filter):
            return None

        haystack = self._package_haystack(package_for_filter)
        is_mcp = self._is_mcp_package(name, description)
        categories = ["Tools"]
        entity_type = "tool"
        metadata: dict[str, Any] = {
            "package": {
                "ecosystem": "npm",
                "package_name": name,
                "version": latest or search_package.get("version"),
                "license": version_doc.get("license") or search_package.get("license"),
                "keywords": keywords,
                "package_date": search_package.get("date") or (package_doc.get("time") or {}).get(latest),
                "updated": search_object.get("updated"),
                "downloads": search_object.get("downloads"),
                "links": search_package.get("links") or {},
                "query": query,
            }
        }
        if is_mcp:
            entity_type = "mcp"
            categories.append("MCP")
            metadata["mcp"] = {
                "installation_method": f"npm package {name}",
                "runtime_requirements": version_doc.get("engines"),
                "package_name": name,
                "version": latest or search_package.get("version"),
                "deprecated": version_doc.get("deprecated"),
                "bin": version_doc.get("bin"),
            }
        if any(term in haystack for term in CREATIVE_TERMS):
            categories.append("Creative")

        return RawEntityRecord(
            source_key=f"npm-search:package:{name.lower()}",
            entity_type=entity_type,
            name=name,
            description=description,
            url=normalize_url(npm_url),
            categories=categories,
            source_name=self.name,
            source_url=source_url,
            raw={"search_object": search_object, "package_doc_name": package_doc.get("name"), "dist-tags": package_doc.get("dist-tags")},
            metadata=metadata,
            fetched_at=fetched_at,
        )

    def _registry_url(self, package: str) -> str:
        return "https://registry.npmjs.org/" + package.replace("/", "%2F")

    def _is_mcp_package(self, name: str, description: str) -> bool:
        text = f"{name} {description}".lower()
        if "model context protocol" in text:
            return True
        if "mcp server" in text or "mcp servers" in text or "mcp adapter" in text or "mcp adapters" in text:
            return True
        normalized_name = name.lower().replace("_", "-")
        return normalized_name.endswith("-mcp") or "-mcp-" in normalized_name or "/mcp-" in normalized_name or "/mcp" in normalized_name

    def _package_haystack(self, package: dict[str, Any]) -> str:
        keywords = package.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        return " ".join([str(package.get("name", "")), str(package.get("description", "")), " ".join(map(str, keywords))]).lower()
