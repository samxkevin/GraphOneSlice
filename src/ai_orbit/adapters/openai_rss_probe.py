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
                http_status=response.status_code,
                pagination="feed endpoint; no pagination observed in this probe",
                available_fields=["content-type", content_type] if content_type else [],
                authentication_required=False,
                failure_behavior="HTTP errors or XML parsing failures are source failures, not reasons to synthesize news",
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="RSS/XML",
                access_method="official RSS feed URL",
                url=self.settings.openai_rss_url,
                status="unusable",
                http_status=None,
                authentication_required=False,
                failure_behavior=f"network: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        return []
