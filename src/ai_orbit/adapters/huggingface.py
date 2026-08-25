from __future__ import annotations

from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError


class HuggingFaceProbeAdapter(SourceAdapter):
    """Probe Hugging Face Hub availability without fabricating fallback data."""

    name = "Hugging Face Hub API Probe"

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
        try:
            response = await self.client.get_json(self.settings.huggingface_models_url, params={"limit": 1})
            sample = response.data[0] if isinstance(response.data, list) and response.data else {}
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="Hugging Face public models endpoint",
                url=response.url,
                status="usable",
                domain="Models",
                http_status=response.status_code,
                pagination="limit parameter observed; additional pagination not used in this vertical slice",
                available_fields=list(sample.keys())[:40],
                required_fields=["model id", "model URL", "provider/author", "license", "modalities", "timestamps"],
                authentication_required=False,
                freshness="model timestamps to be inspected before ingestion",
                anti_bot_js="API JSON endpoint if reachable; no browser automation intended",
                inventory_evidence="sampled limit=1 response returned at least one model" if sample else None,
                ai_relevance="candidate model hub source",
                actual_crawl_feasibility="usable only if endpoint remains reachable and fields validate",
                failure_behavior="429/5xx retryable; malformed JSON rejected",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="Hugging Face public models endpoint",
                url=self.settings.huggingface_models_url,
                status="unusable",
                domain="Models",
                http_status=exc.status_code,
                required_fields=["model id", "model URL", "provider/author", "license", "modalities", "timestamps"],
                authentication_required=False,
                anti_bot_js="not determined; request failed before content inspection",
                ai_relevance="candidate model hub source",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        # A probe adapter intentionally returns no data unless verify succeeds
        # and a real model adapter is enabled. This prevents replacing an
        # inaccessible source with fabricated model records.
        return []
