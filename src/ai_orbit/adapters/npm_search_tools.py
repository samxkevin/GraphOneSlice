from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url


AI_RELEVANCE_TOKENS = {
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
    "agents",
    "agentic",
    "mcp",
    "comfyui",
    "langchain",
    "ollama",
    "generative",
}

WEAK_KEYWORD_ONLY_TOKENS = {"ai", "llm", "gpt", "agent", "agents", "generative"}
AMBIGUOUS_AI_EVIDENCE_SIGNALS = {"ai", "llm", "gpt", "agent", "agents", "generative"}

AI_RELEVANCE_PHRASES = {
    "model context protocol",
    "stable diffusion",
    "ai sdk",
    "language model",
    "tool calling",
    "structured output",
}

CREATIVE_TOKENS = {"comfyui", "image", "video", "audio", "creative"}
CREATIVE_PHRASES = {"stable diffusion", "image generation", "video generation", "audio generation"}


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
        return self._has_ai_relevance_evidence(package)

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
        package_for_filter = {
            "name": name,
            "description": description,
            "keywords": keywords,
            "links": {"npm": npm_url},
            "readme": package_doc.get("readme") or "",
        }
        if not self._is_candidate_package(package_for_filter):
            return None

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
                "ai_relevance_evidence": self._first_signal_evidence(
                    package_for_filter,
                    AI_RELEVANCE_TOKENS,
                    AI_RELEVANCE_PHRASES,
                    fields=("name", "description", "readme", "keywords"),
                    include_gpt_compact=True,
                ),
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
        if self._has_creative_evidence(package_for_filter):
            categories.append("Creative")
            metadata["package"]["creative_category_evidence"] = self._first_signal_evidence(
                package_for_filter,
                CREATIVE_TOKENS,
                CREATIVE_PHRASES,
                fields=("name", "description"),
                include_gpt_compact=False,
            )

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

    def _has_ai_relevance_evidence(self, package: dict[str, Any]) -> bool:
        # Name/description/README are strong evidence because they describe the
        # package itself. Keyword-only matches require multiple explicit signals
        # and at least one signal stronger than generic ai/llm/gpt/agent tags.
        strong_text = " ".join(self._package_text_by_field(package, fields=("name", "description", "readme")).values())
        strong_text_signals = self._ai_signals_for_text(strong_text)
        if strong_text_signals and not strong_text_signals <= {"agent", "agents"}:
            return True

        keyword_signals = self._ai_signals_for_text(self._keywords_text(package))
        strong_keyword_signals = keyword_signals - WEAK_KEYWORD_ONLY_TOKENS
        return len(keyword_signals) >= 2 and bool(strong_keyword_signals)

    def _has_creative_evidence(self, package: dict[str, Any]) -> bool:
        # Creative is a semantic category, so do not assign it from keyword-only
        # metadata or broad README mentions/images. Require package name or
        # package description evidence.
        creative_text = " ".join(self._package_text_by_field(package, fields=("name", "description")).values())
        return bool(self._signals_for_text(creative_text, CREATIVE_TOKENS, CREATIVE_PHRASES, include_gpt_compact=False))

    def _ai_signals_for_text(self, text: str) -> set[str]:
        return self._signals_for_text(text, AI_RELEVANCE_TOKENS, AI_RELEVANCE_PHRASES, include_gpt_compact=True)

    def _signals_for_text(self, text: str, tokens: set[str], phrases: set[str], *, include_gpt_compact: bool) -> set[str]:
        tokenized = set(re.findall(r"[a-z0-9]+", text.lower()))
        signals = set(tokenized & tokens)
        if include_gpt_compact:
            signals.update(token for token in tokenized if re.fullmatch(r"gpt\d+[a-z0-9]*", token))
        normalized = f" {re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()} "
        signals.update(phrase for phrase in phrases if f" {phrase} " in normalized)
        return signals

    def _first_signal_evidence(
        self,
        package: dict[str, Any],
        tokens: set[str],
        phrases: set[str],
        *,
        fields: tuple[str, ...],
        include_gpt_compact: bool,
    ) -> dict[str, Any] | None:
        for field, text in self._package_text_by_field(package, fields=fields).items():
            signals = self._signals_for_text(text, tokens, phrases, include_gpt_compact=include_gpt_compact)
            if include_gpt_compact and field in {"name", "keywords"} and signals <= AMBIGUOUS_AI_EVIDENCE_SIGNALS:
                continue
            if signals:
                return {
                    "field": field,
                    "signals": sorted(signals),
                    "excerpt": self._evidence_excerpt(text, signals),
                }
        return None

    def _evidence_excerpt(self, text: str, signals: set[str]) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= 240:
            return compact
        lower = compact.lower()
        positions = [lower.find(signal.lower()) for signal in signals if lower.find(signal.lower()) >= 0]
        start = max(min(positions) - 80, 0) if positions else 0
        return compact[start : start + 240].strip()

    def _package_text_by_field(self, package: dict[str, Any], *, fields: tuple[str, ...]) -> dict[str, str]:
        values: dict[str, str] = {}
        for field in fields:
            if field == "keywords":
                value = self._keywords_text(package)
            else:
                raw_value = package.get(field)
                value = raw_value if isinstance(raw_value, str) else ""
            if value.strip():
                values[field] = value
        return values

    def _keywords_text(self, package: dict[str, Any]) -> str:
        keywords = package.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        return " ".join(map(str, keywords))
