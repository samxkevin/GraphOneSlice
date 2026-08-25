from __future__ import annotations

import httpx

from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility


class OpenAIRssProbeAdapter(SourceAdapter):
    """Checks an official OpenAI feed endpoint and records failures explicitly."""

    name = "OpenAI News RSS Probe"

    def __init__(self, settings: AIOrbitSettings):
        self.settings = settings

    async def verify(self) -> SourceFeasibility:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.http_timeout_seconds,
                verify=self.settings.ca_bundle,
                headers={"User-Agent": "GraphOneSlice-AIOrbit-VerticalSlice/0.1"},
                follow_redirects=True,
            ) as client:
                response = await client.get(self.settings.openai_rss_url)
            status = "usable" if response.status_code < 400 else "unusable"
            content_type = response.headers.get("content-type", "")
            return SourceFeasibility(
                source_name=self.name,
                source_type="RSS/XML",
                access_method="official RSS feed URL",
                url=str(response.url),
                status=status,  # type: ignore[arg-type]
                domain="News",
                http_status=response.status_code,
                pagination="feed endpoint; no pagination observed in this probe",
                available_fields=["content-type", content_type] if content_type else [],
                required_fields=["title", "URL", "publication timestamp", "description/content"],
                authentication_required=False,
                freshness="publication timestamp required before accepting news records",
                anti_bot_js="RSS/XML feed if reachable; no browser automation intended",
                ai_relevance="official OpenAI news feed candidate",
                actual_crawl_feasibility="usable only if feed is reachable and timestamps parse",
                failure_behavior="HTTP errors or XML parsing failures are source failures, not reasons to synthesize news",
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="RSS/XML",
                access_method="official RSS feed URL",
                url=self.settings.openai_rss_url,
                status="unusable",
                domain="News",
                http_status=None,
                required_fields=["title", "URL", "publication timestamp", "description/content"],
                authentication_required=False,
                freshness="publication timestamp required but feed unavailable in this environment",
                anti_bot_js="not determined; request failed before content inspection",
                ai_relevance="official OpenAI news feed candidate",
                actual_crawl_feasibility="not usable from this environment based on observed network failure",
                failure_behavior=f"network: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        return []
