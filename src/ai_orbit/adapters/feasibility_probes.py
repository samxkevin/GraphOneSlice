from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility


@dataclass(frozen=True)
class ProbeDefinition:
    source_name: str
    domain: str
    source_type: str
    access_method: str
    url: str
    required_fields: list[str]
    pagination: str | None = None
    authentication_required: bool | None = None
    freshness: str | None = None
    anti_bot_js: str | None = None
    inventory_evidence: str | None = None
    company_identity_quality: str | None = None
    ai_relevance: str | None = None
    actual_crawl_feasibility: str | None = None
    record_volume_estimate: str | None = None
    expected_status_if_http_ok: str = "partial"
    headers: dict[str, str] = field(default_factory=dict)


class CandidateSourceProbeAdapter(SourceAdapter):
    """Feasibility-only adapter.

    It records observed accessibility and response shape for candidate sources
    without ingesting records. Production ingestion adapters should be added only
    after a probe demonstrates usable source-backed fields.
    """

    def __init__(self, settings: AIOrbitSettings, definition: ProbeDefinition):
        self.settings = settings
        self.definition = definition
        self.name = definition.source_name

    async def verify(self) -> SourceFeasibility:
        headers = {
            "User-Agent": "GraphOneSlice-AIOrbit-Feasibility/0.1",
            "Accept": "application/json, application/rss+xml, application/xml;q=0.8, text/html;q=0.5, */*;q=0.1",
        }
        headers.update(self.definition.headers)
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.http_timeout_seconds,
                verify=self.settings.ca_bundle,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(self.definition.url)
        except httpx.TimeoutException as exc:
            return self._failure(f"timeout: {exc}")
        except httpx.RequestError as exc:
            return self._failure(f"network: {exc}")

        content_type = response.headers.get("content-type", "")
        available_fields = ["content-type"]
        status: str = self.definition.expected_status_if_http_ok
        failure_behavior = None
        inventory = self.definition.inventory_evidence

        if response.status_code >= 400:
            status = "unusable"
            failure_behavior = f"HTTP {response.status_code} returned during feasibility probe"
        else:
            body = response.text[:5000]
            if "json" in content_type:
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        available_fields = list(payload.keys())[:40]
                        if "objects" in payload and isinstance(payload["objects"], list):
                            inventory = f"JSON response contained {len(payload['objects'])} objects in sampled page"
                        elif "jobs" in payload and isinstance(payload["jobs"], list):
                            inventory = f"JSON response contained {len(payload['jobs'])} jobs in sampled page"
                        elif "data" in payload and isinstance(payload["data"], list):
                            inventory = f"JSON response contained {len(payload['data'])} data rows in sampled page"
                    elif isinstance(payload, list):
                        available_fields = list(payload[0].keys())[:40] if payload and isinstance(payload[0], dict) else ["list"]
                        inventory = f"JSON response contained {len(payload)} rows in sampled page"
                except ValueError:
                    status = "unusable"
                    failure_behavior = "malformed JSON during feasibility probe"
            elif "xml" in content_type or "rss" in content_type or body.lstrip().startswith("<?xml"):
                available_fields = ["rss/xml text", "content-type"]
                inventory = inventory or "RSS/XML response body was reachable; item count not parsed by generic probe"
            else:
                available_fields = ["html/text", "content-type"]
                inventory = inventory or "HTML/text response body was reachable; record extraction not verified"

        return SourceFeasibility(
            source_name=self.definition.source_name,
            source_type=self.definition.source_type,
            access_method=self.definition.access_method,
            url=str(response.url),
            status=status,  # type: ignore[arg-type]
            domain=self.definition.domain,
            http_status=response.status_code,
            pagination=self.definition.pagination,
            available_fields=available_fields,
            required_fields=self.definition.required_fields,
            authentication_required=self.definition.authentication_required,
            rate_limit_observed={k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"},
            freshness=self.definition.freshness,
            anti_bot_js=self.definition.anti_bot_js,
            inventory_evidence=inventory,
            company_identity_quality=self.definition.company_identity_quality,
            ai_relevance=self.definition.ai_relevance,
            actual_crawl_feasibility=self.definition.actual_crawl_feasibility,
            record_volume_estimate=self.definition.record_volume_estimate,
            failure_behavior=failure_behavior or "probe completed without ingestion; source still requires a dedicated adapter before records are accepted",
        )

    async def discover(self) -> list[RawEntityRecord]:
        return []

    def _failure(self, failure_behavior: str) -> SourceFeasibility:
        return SourceFeasibility(
            source_name=self.definition.source_name,
            source_type=self.definition.source_type,
            access_method=self.definition.access_method,
            url=self.definition.url,
            status="unusable",
            domain=self.definition.domain,
            http_status=None,
            pagination=self.definition.pagination,
            available_fields=[],
            required_fields=self.definition.required_fields,
            authentication_required=self.definition.authentication_required,
            freshness=self.definition.freshness,
            anti_bot_js=self.definition.anti_bot_js or "not determined; request failed before content inspection",
            inventory_evidence=self.definition.inventory_evidence,
            company_identity_quality=self.definition.company_identity_quality,
            ai_relevance=self.definition.ai_relevance,
            actual_crawl_feasibility="not usable from this environment based on observed network failure",
            record_volume_estimate=self.definition.record_volume_estimate,
            failure_behavior=failure_behavior,
        )


def build_candidate_probe_adapters(settings: AIOrbitSettings) -> list[CandidateSourceProbeAdapter]:
    definitions = [
        ProbeDefinition(
            source_name="Y Combinator Companies AI Probe",
            domain="Startups/Companies",
            source_type="HTML",
            access_method="public web page probe",
            url="https://www.ycombinator.com/companies?industry=AI",
            required_fields=["company name", "company URL", "description", "batch/year", "AI relevance"],
            pagination="not verified; request failed before page behavior could be inspected",
            authentication_required=False,
            freshness="company profile freshness not verified",
            ai_relevance="candidate startup/company source filtered by AI industry URL parameter",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="Product Hunt GraphQL Probe",
            domain="Products",
            source_type="API/GraphQL",
            access_method="public GraphQL endpoint probe",
            url="https://api.producthunt.com/v2/api/graphql",
            required_fields=["product name", "tagline/description", "product URL", "launch/publication date", "maker/company", "AI relevance"],
            pagination="GraphQL pagination not verified; request failed before schema inspection",
            authentication_required=None,
            freshness="launch timestamp not verified",
            ai_relevance="candidate product source; no product records accepted until API access and fields are verified",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="Hacker News Algolia AI Stories Probe",
            domain="News",
            source_type="API/JSON",
            access_method="HN Algolia search_by_date API probe",
            url="https://hn.algolia.com/api/v1/search_by_date?query=artificial%20intelligence&tags=story&hitsPerPage=3",
            required_fields=["title", "URL/story URL", "created_at story timestamp", "author", "objectID", "AI relevance"],
            pagination="page and hitsPerPage parameters expected by endpoint convention; not verified because request failed before response inspection",
            authentication_required=False,
            freshness="created_at would be Hacker News story submission time if reachable; external article publication time is not established by this probe",
            anti_bot_js="API-first JSON endpoint expected; no browser automation intended, but accessibility failed before response inspection",
            ai_relevance="candidate news/story source searched by artificial intelligence query; downstream title/URL/content filtering would be required",
            actual_crawl_feasibility="not usable from this environment based on observed TLS/network failure",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="Himalayas AI Jobs API Probe",
            domain="Jobs",
            source_type="API/JSON",
            access_method="Himalayas remote jobs search API probe",
            url="https://himalayas.app/jobs/api/search?q=artificial%20intelligence&limit=3",
            required_fields=["job title", "company", "job URL", "location", "posted/created timestamp", "source"],
            pagination="offset/limit or page parameters documented by source, but not verified because request failed before response inspection",
            authentication_required=False,
            freshness="posting timestamp semantics not verified because endpoint was not reachable from this environment",
            anti_bot_js="API-first JSON endpoint expected; request failed before content inspection",
            ai_relevance="candidate jobs source searched by artificial intelligence query; downstream title/description filtering required",
            actual_crawl_feasibility="not usable from this environment based on observed TLS/network failure",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="GDELT AI News API Probe",
            domain="News",
            source_type="API/JSON",
            access_method="GDELT 2.1 DOC API article list probe",
            url="https://api.gdeltproject.org/api/v2/doc/doc?query=artificial%20intelligence&mode=artlist&format=json&maxrecords=3",
            required_fields=["title", "canonical article URL", "source/domain", "publication timestamp", "AI relevance"],
            pagination="maxrecords/startdatetime/enddatetime parameters are documented by source, but not verified because request failed before response inspection",
            authentication_required=False,
            freshness="GDELT seendate would need separate validation and is not assumed to be publisher publication time",
            anti_bot_js="API-first JSON endpoint expected; request failed before content inspection",
            ai_relevance="candidate AI news search source; downstream article relevance filtering required",
            actual_crawl_feasibility="not usable from this environment based on observed TLS/network failure",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="Models.dev Model Metadata API Probe",
            domain="Models",
            source_type="API/JSON",
            access_method="models.dev public model metadata JSON probe",
            url="https://models.dev/api.json",
            required_fields=["provider", "model id", "modalities or capabilities", "model URL/source", "license if available"],
            pagination="single JSON document expected, but not verified because request failed before response inspection",
            authentication_required=False,
            freshness="model metadata freshness not verified because endpoint was not reachable from this environment",
            anti_bot_js="API-first JSON endpoint expected; request failed before content inspection",
            ai_relevance="candidate model metadata enrichment source",
            actual_crawl_feasibility="not usable from this environment based on observed TLS/network failure",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="NPM Search AI Packages Probe",
            domain="Products/Tools",
            source_type="API/JSON",
            access_method="NPM registry search endpoint",
            url="https://registry.npmjs.org/-/v1/search?text=keywords:ai&size=5",
            required_fields=["package name", "description", "version/date", "repository or homepage", "maintainer/publisher"],
            pagination="size/from search parameters observed by endpoint convention; not used for ingestion in this milestone",
            authentication_required=False,
            freshness="package date fields may be update times, not product launch dates",
            anti_bot_js="NPM registry JSON endpoint is API-first; no JavaScript required",
            ai_relevance="keyword search can find AI-related packages but package identity is not automatically product identity",
            actual_crawl_feasibility="partial: endpoint reachable, but a dedicated adapter must filter packages conservatively before treating them as products/tools",
            record_volume_estimate="search endpoint exposes sampled page; full inventory not measured",
        ),
        ProbeDefinition(
            source_name="OpenRouter Models API Probe",
            domain="Models",
            source_type="API/JSON",
            access_method="public models endpoint probe",
            url="https://openrouter.ai/api/v1/models",
            required_fields=["model id", "model name", "provider", "license", "modalities", "model URL"],
            pagination="not verified; request failed before response inspection",
            authentication_required=None,
            freshness="model update/publication timestamps not verified",
            ai_relevance="candidate model catalog source",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="TechCrunch AI RSS Probe",
            domain="News",
            source_type="RSS/XML",
            access_method="RSS feed probe",
            url="https://techcrunch.com/category/artificial-intelligence/feed/",
            required_fields=["title", "URL", "publication timestamp", "description", "AI category"],
            pagination="RSS feed page only; historical pagination not verified",
            authentication_required=False,
            freshness="publication timestamp required but feed unavailable in this environment",
            ai_relevance="candidate AI news feed",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="VentureBeat AI RSS Probe",
            domain="News",
            source_type="RSS/XML",
            access_method="RSS feed probe",
            url="https://venturebeat.com/category/ai/feed/",
            required_fields=["title", "URL", "publication timestamp", "description", "AI category"],
            pagination="RSS feed page only; historical pagination not verified",
            authentication_required=False,
            freshness="publication timestamp required but feed unavailable in this environment",
            ai_relevance="candidate AI news feed",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="Remotive AI Jobs API Probe",
            domain="Jobs",
            source_type="API/JSON",
            access_method="jobs API search endpoint probe",
            url="https://remotive.com/api/remote-jobs?search=ai",
            required_fields=["job title", "company", "listing URL", "location", "publication timestamp", "AI relevance"],
            pagination="not verified; request failed before response inspection",
            authentication_required=False,
            freshness="publication timestamp required but endpoint unavailable in this environment",
            ai_relevance="candidate jobs source searched by AI keyword",
            record_volume_estimate="unknown from this environment",
        ),
        ProbeDefinition(
            source_name="RemoteOK Jobs API Probe",
            domain="Jobs",
            source_type="API/JSON",
            access_method="jobs API endpoint probe",
            url="https://remoteok.com/api",
            required_fields=["job title", "company", "listing URL", "location", "publication timestamp", "tags/AI relevance"],
            pagination="not verified; request failed before response inspection",
            authentication_required=False,
            freshness="publication timestamp required but endpoint unavailable in this environment",
            ai_relevance="candidate remote jobs API requiring downstream AI tag filtering",
            record_volume_estimate="unknown from this environment",
        ),
    ]
    return [CandidateSourceProbeAdapter(settings, definition) for definition in definitions]
