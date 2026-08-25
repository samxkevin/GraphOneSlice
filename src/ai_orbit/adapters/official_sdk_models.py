from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url


@dataclass(frozen=True)
class ProviderModelSource:
    provider_id: str
    provider_name: str
    company_source_key: str
    repository: str
    api_url: str
    html_url: str
    type_name: str
    preferred_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class ObservedModelIdentifier:
    identifier: str
    line_number: int


class OfficialSDKModelAdapter(SourceAdapter):
    """Extracts model identifiers from official provider SDK type files.

    This is intentionally conservative: the source files prove that these
    identifiers are present in official SDK type definitions. They do not prove
    license, modality, pricing, or capability, so those fields remain null.
    """

    name = "Official SDK Model Definitions"

    SOURCES: tuple[ProviderModelSource, ...] = (
        ProviderModelSource(
            provider_id="openai",
            provider_name="OpenAI",
            company_source_key="official-sdk:company:openai",
            repository="openai/openai-python",
            api_url="https://api.github.com/repos/openai/openai-python/contents/src/openai/types/shared/chat_model.py",
            html_url="https://github.com/openai/openai-python/blob/main/src/openai/types/shared/chat_model.py",
            type_name="ChatModel",
            preferred_identifiers=("gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini"),
        ),
        ProviderModelSource(
            provider_id="anthropic",
            provider_name="Anthropic",
            company_source_key="official-sdk:company:anthropic",
            repository="anthropics/anthropic-sdk-python",
            api_url="https://api.github.com/repos/anthropics/anthropic-sdk-python/contents/src/anthropic/types/model.py",
            html_url="https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/model.py",
            type_name="Model",
            preferred_identifiers=(
                "claude-sonnet-5",
                "claude-opus-5",
                "claude-haiku-4-5",
                "claude-opus-4-5",
                "claude-sonnet-4-5",
                "claude-mythos-preview",
                "claude-opus-4-8",
                "claude-opus-4-7",
            ),
        ),
    )

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
        self._cache: dict[str, tuple[ProviderModelSource, list[ObservedModelIdentifier], str]] = {}
        self._failures: list[str] = []

    async def verify(self) -> SourceFeasibility:
        available_fields: set[str] = set()
        parsed_counts: list[str] = []
        self._cache.clear()
        self._failures.clear()
        for source in self.SOURCES:
            try:
                text, response_url, fields = await self._fetch_source_text(source)
                observed = self._parse_model_identifiers(text)
                if not observed:
                    self._failures.append(f"{source.repository}: no model identifiers parsed")
                    continue
                self._cache[source.provider_id] = (source, observed, response_url)
                available_fields.update(fields)
                parsed_counts.append(f"{source.provider_name}: {len(observed)} identifiers")
            except SourceFetchError as exc:
                self._failures.append(f"{source.repository}: {exc.failure_class.value}: {exc}")

        if self._cache and self._failures:
            status = "partial"
        elif self._cache:
            status = "usable"
        else:
            status = "unusable"
        return SourceFeasibility(
            source_name=self.name,
            source_type="API/JSON + source file content",
            access_method="GitHub REST contents API for official provider SDK model type files",
            url="; ".join(source.api_url for source in self.SOURCES),
            status=status,  # type: ignore[arg-type]
            domain="Models",
            http_status=200 if self._cache else None,
            pagination="not paginated; one GitHub contents response per SDK type file",
            available_fields=sorted(available_fields),
            required_fields=["provider SDK repository", "source file content", "model identifier literal"],
            authentication_required=False,
            rate_limit_observed={},
            freshness="GitHub contents response reflects the current default branch at fetch time; model launch/publication time is not supplied",
            anti_bot_js="GitHub REST API returned JSON; no browser automation or JavaScript required",
            inventory_evidence="; ".join(parsed_counts) if parsed_counts else None,
            company_identity_quality="provider inferred from official SDK repository owner/name; company records are merged by deterministic normalized name",
            ai_relevance="source files are provider SDK model type definitions",
            actual_crawl_feasibility="usable for a bounded model sample; not a complete model catalog because SDK type files do not expose all metadata",
            record_volume_estimate="bounded sample configured by AI_ORBIT_OFFICIAL_SDK_MODEL_LIMIT_PER_PROVIDER",
            failure_behavior="; ".join(self._failures) if self._failures else "429/5xx retryable; 403/404/malformed JSON recorded as source failures",
        )

    async def discover(self) -> list[RawEntityRecord]:
        if not self._cache:
            # verify() normally populates this. Keep discover safe if called directly.
            await self.verify()
        records: list[RawEntityRecord] = []
        now = datetime.now(timezone.utc)
        for provider_id, (source, observed, response_url) in self._cache.items():
            company_record = self._company_record(source, response_url, fetched_at=now)
            records.append(company_record)
            selected = self._select_sample(source, observed)
            for model in selected:
                records.append(self._model_record(source, model, response_url, fetched_at=now))
        return records

    async def _fetch_source_text(self, source: ProviderModelSource) -> tuple[str, str, list[str]]:
        response = await self.client.get_json(source.api_url)
        data = response.data
        fields = list(data.keys()) if isinstance(data, dict) else []
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"unexpected GitHub contents payload for {source.api_url}")
        # GitHub contents API returns base64 text for small files. The API also
        # provides a download_url, but raw.githubusercontent.com was not assumed
        # reachable in this environment.
        import base64

        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, f"missing base64 content for {source.api_url}")
        text = base64.b64decode(content).decode("utf-8", "replace")
        return text, response.url, fields

    def _parse_model_identifiers(self, text: str) -> list[ObservedModelIdentifier]:
        observed: list[ObservedModelIdentifier] = []
        seen: set[str] = set()
        for match in re.finditer(r'"([^"\n]+)"', text):
            identifier = match.group(1)
            if identifier in seen:
                continue
            seen.add(identifier)
            line_number = text.count("\n", 0, match.start()) + 1
            observed.append(ObservedModelIdentifier(identifier=identifier, line_number=line_number))
        return observed

    def _select_sample(self, source: ProviderModelSource, observed: list[ObservedModelIdentifier]) -> list[ObservedModelIdentifier]:
        by_identifier = {item.identifier: item for item in observed}
        selected: list[ObservedModelIdentifier] = []
        for identifier in source.preferred_identifiers:
            item = by_identifier.get(identifier)
            if item is not None:
                selected.append(item)
            if len(selected) >= self.settings.official_sdk_model_limit_per_provider:
                return selected
        for item in observed:
            if item.identifier in {existing.identifier for existing in selected}:
                continue
            selected.append(item)
            if len(selected) >= self.settings.official_sdk_model_limit_per_provider:
                break
        return selected

    def _company_record(self, source: ProviderModelSource, source_url: str, *, fetched_at: datetime) -> RawEntityRecord:
        return RawEntityRecord(
            source_key=source.company_source_key,
            entity_type="company",
            name=source.provider_name,
            description=f"{source.provider_name} is the provider named by the official SDK repository {source.repository} used for model identifier evidence.",
            url=normalize_url(f"https://github.com/{source.repository.split('/')[0]}"),
            categories=["Companies"],
            source_name=self.name,
            source_url=source_url,
            raw={"provider_name": source.provider_name, "repository": source.repository, "type_name": source.type_name},
            metadata={"company": {"founding_year": None, "industry_sector": None, "headquarters": None}},
            fetched_at=fetched_at,
        )

    def _model_record(
        self,
        source: ProviderModelSource,
        model: ObservedModelIdentifier,
        source_url: str,
        *,
        fetched_at: datetime,
    ) -> RawEntityRecord:
        entity_url = f"{source.html_url}#L{model.line_number}"
        return RawEntityRecord(
            source_key=f"official-sdk:model:{source.provider_id}:{model.identifier}",
            entity_type="model",
            name=model.identifier,
            description=f"Model identifier `{model.identifier}` observed in the {source.type_name} type definition from the official {source.provider_name} SDK repository {source.repository}.",
            url=normalize_url(entity_url),
            categories=["Models"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "provider": source.provider_name,
                "repository": source.repository,
                "type_name": source.type_name,
                "model_identifier": model.identifier,
                "line_number": model.line_number,
            },
            metadata={
                "model": {
                    "license": None,
                    "modalities": None,
                    "provider": source.provider_name,
                    "model_identifier": model.identifier,
                    "source_repository": source.repository,
                    "source_type_name": source.type_name,
                    "source_line": model.line_number,
                }
            },
            pending_relationships=[
                {
                    "relationship_type": "develops",
                    "direction": "target_is_self",
                    "other_source_key": source.company_source_key,
                    "method": "official_sdk_model_literal",
                    "evidence": {
                        "model_identifier": model.identifier,
                        "source_repository": source.repository,
                        "source_type_name": source.type_name,
                        "line_number": model.line_number,
                        "source_url": source_url,
                    },
                }
            ],
            fetched_at=fetched_at,
        )
