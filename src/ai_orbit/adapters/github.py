from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url


class GitHubAdapter(SourceAdapter):
    name = "GitHub API"

    def __init__(self, settings: AIOrbitSettings):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GraphOneSlice-AIOrbit-VerticalSlice/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.settings = settings
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

    async def verify(self) -> SourceFeasibility:
        url = f"{self.settings.github_api_base.rstrip('/')}/search/repositories"
        try:
            response = await self.client.get_json(
                url,
                params={"q": self.settings.github_search_query, "sort": "stars", "order": "desc", "per_page": 1},
            )
            data = response.data
            first = (data.get("items") or [{}])[0]
            rate = {k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit")}
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="GitHub REST search/repository/org endpoints",
                url=response.url,
                status="usable",
                http_status=response.status_code,
                pagination="page/per_page parameters; Link header appears when additional pages are available",
                available_fields=list(first.keys())[:40],
                authentication_required=False,
                rate_limit_observed=rate,
                failure_behavior="429 and 5xx are retryable; 403/404 are non-retryable source failures",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="GitHub REST search/repository/org endpoints",
                url=url,
                status="unusable",
                http_status=exc.status_code,
                authentication_required=False,
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        records: list[RawEntityRecord] = []
        now = datetime.now(timezone.utc)
        search_url = f"{self.settings.github_api_base.rstrip('/')}/search/repositories"
        response = await self.client.get_json(
            search_url,
            params={
                "q": self.settings.github_search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": self.settings.github_search_limit,
            },
        )
        for item in response.data.get("items", []):
            record = self._repo_record(item, source_url=item.get("url") or response.url, fetched_at=now)
            if record is not None:
                records.append(record)

        # A small set of AI ecosystem organizations with official GitHub org
        # metadata. These records are source-backed org observations, not
        # synthetic company profiles.
        for org in self.settings.github_company_orgs:
            org_url = f"{self.settings.github_api_base.rstrip('/')}/orgs/{org}"
            try:
                org_response = await self.client.get_json(org_url)
            except SourceFetchError:
                continue
            org_record = self._org_record(org_response.data, org_response.url, fetched_at=now)
            if org_record is not None:
                records.append(org_record)
        return records

    def _repo_record(self, item: dict[str, Any], *, source_url: str, fetched_at: datetime) -> RawEntityRecord | None:
        full_name = item.get("full_name")
        description = (item.get("description") or "").strip()
        html_url = item.get("html_url")
        if not full_name or not description or not html_url:
            return None
        topics = item.get("topics") or []
        categories = ["Repositories"]
        lowered = " ".join([description, full_name, " ".join(topics)]).lower()
        if any(token in lowered for token in ["tool", "agent", "sdk", "api", "llm", "chatgpt", "gpt"]):
            categories.append("Tools")
        if "awesome" in lowered or "awesome-list" in topics:
            categories.append("Collections")
        if "prompt" in lowered:
            categories.append("Creative")
        if item.get("created_at", "") >= "2025-01-01":
            categories.append("New/Recently Added")

        owner = item.get("owner") or {}
        pending: list[dict[str, Any]] = []
        if owner.get("type") == "Organization" and owner.get("login"):
            pending.append({
                "relationship_type": "develops",
                "direction": "target_is_self",
                "other_source_key": f"github:org:{owner['login'].lower()}",
                "method": "github_repository_owner",
                "evidence": {
                    "field": "owner.login",
                    "value": owner.get("login"),
                    "source_url": source_url,
                },
            })
        return RawEntityRecord(
            source_key=f"github:repo:{full_name.lower()}",
            entity_type="repository",
            name=full_name,
            description=description,
            url=normalize_url(html_url),
            categories=categories,
            source_name=self.name,
            source_url=source_url,
            raw=item,
            metadata={
                "repository": {
                    "stars": item.get("stargazers_count"),
                    "primary_language": item.get("language"),
                    "last_updated_timestamp": item.get("updated_at"),
                    "full_name": full_name,
                    "topics": topics,
                }
            },
            pending_relationships=pending,
            fetched_at=fetched_at,
        )

    def _org_record(self, org: dict[str, Any], source_url: str, *, fetched_at: datetime) -> RawEntityRecord | None:
        login = org.get("login")
        name = (org.get("name") or login or "").strip()
        description = (org.get("description") or "").strip()
        html_url = org.get("html_url")
        if not login or not name or not html_url or not description:
            return None
        return RawEntityRecord(
            source_key=f"github:org:{login.lower()}",
            entity_type="company",
            name=name,
            description=description,
            url=normalize_url(html_url),
            categories=["Companies"],
            source_name=self.name,
            source_url=source_url,
            raw=org,
            metadata={
                "company": {
                    "founding_year": None,
                    "industry_sector": None,
                    "headquarters": None,
                    "github_login": login,
                    "github_blog": org.get("blog"),
                    "github_location_observed": org.get("location"),
                }
            },
            fetched_at=fetched_at,
        )
