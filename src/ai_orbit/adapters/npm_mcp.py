from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.url import normalize_url


class NpmMcpAdapter(SourceAdapter):
    name = "NPM Registry MCP Packages"

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
        package = self.settings.npm_mcp_packages[0]
        url = self._registry_url(package)
        try:
            response = await self.client.get_json(url)
            latest = response.data.get("dist-tags", {}).get("latest")
            version = response.data.get("versions", {}).get(latest, {}) if latest else {}
            fields = sorted(set(response.data.keys()) | set(version.keys()))
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="NPM registry package document",
                url=response.url,
                status="usable",
                domain="MCP/Tools",
                http_status=response.status_code,
                pagination="not paginated for a single package document; versions are nested by version key",
                available_fields=fields[:40],
                required_fields=["name", "description", "dist-tags.latest", "versions[latest].bin", "versions[latest].deprecated", "readme"],
                authentication_required=False,
                rate_limit_observed={},
                freshness="package version/update metadata exists, but not treated as product/news publication time",
                anti_bot_js="NPM registry JSON endpoint returned JSON; no browser automation or JavaScript required",
                inventory_evidence=f"configured MCP packages={len(self.settings.npm_mcp_packages)}; sample package={package}",
                company_identity_quality="MCP package records identify packages, not company profiles",
                ai_relevance="configured allowlist contains Model Context Protocol server packages",
                actual_crawl_feasibility="usable for configured package list; NPM search requires additional filtering before product-scale ingestion",
                record_volume_estimate=str(len(self.settings.npm_mcp_packages)),
                failure_behavior="404 is package not found; 429/5xx are retryable; deprecated packages are retained with metadata rather than fabricated away",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="NPM registry package document",
                url=url,
                status="unusable",
                domain="MCP/Tools",
                http_status=exc.status_code,
                required_fields=["name", "description", "dist-tags.latest", "versions[latest].bin", "versions[latest].deprecated", "readme"],
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        records: list[RawEntityRecord] = []
        now = datetime.now(timezone.utc)
        for package in self.settings.npm_mcp_packages:
            response = await self.client.get_json(self._registry_url(package))
            record = self._package_record(package, response.data, response.url, fetched_at=now)
            if record is not None:
                records.append(record)
                # The legacy GitHub MCP package explicitly says it is for the
                # GitHub API. Create the target tool from that same evidence.
                description = record.description.lower()
                if "github api" in description:
                    tool = self._github_api_tool(response.url, fetched_at=now)
                    records.append(tool)
                    record.pending_relationships.append({
                        "relationship_type": "integrates_with",
                        "direction": "source_is_self",
                        "other_source_key": tool.source_key,
                        "method": "npm_package_description",
                        "evidence": {
                            "field": "description",
                            "value": record.description,
                            "source_url": response.url,
                        },
                    })
        return records

    def _registry_url(self, package: str) -> str:
        return "https://registry.npmjs.org/" + package.replace("/", "%2F")

    def _package_record(self, package: str, data: dict[str, Any], source_url: str, *, fetched_at: datetime) -> RawEntityRecord | None:
        latest = data.get("dist-tags", {}).get("latest")
        version = data.get("versions", {}).get(latest, {}) if latest else {}
        name = version.get("name") or data.get("name") or package
        description = (version.get("description") or data.get("description") or "").strip()
        if not name or not description:
            return None
        bin_field = version.get("bin")
        engines = version.get("engines")
        latest_published_at = (data.get("time") or {}).get(latest) if latest else None
        installation_method = f"npm package {name}"
        readme = data.get("readme") or ""
        if "npx" in readme.lower():
            installation_method = f"npx/npm package {name}"
        metadata = {
            "mcp": {
                "installation_method": installation_method,
                "runtime_requirements": engines,
                "package_name": name,
                "version": latest,
                "latest_version_published_at": latest_published_at,
                "deprecated": version.get("deprecated"),
                "bin": bin_field,
            }
        }
        categories = ["MCP", "Tools"]
        if self._is_recent_package_release(latest_published_at):
            categories.append("New/Recently Added")
        return RawEntityRecord(
            source_key=f"npm:package:{name.lower()}",
            entity_type="mcp",
            name=name,
            description=description,
            url=normalize_url(source_url),
            categories=categories,
            source_name=self.name,
            source_url=source_url,
            raw={
                "name": data.get("name"),
                "dist-tags": data.get("dist-tags"),
                "latest_version": version,
            },
            metadata=metadata,
            fetched_at=fetched_at,
        )

    def _github_api_tool(self, source_url: str, *, fetched_at: datetime) -> RawEntityRecord:
        return RawEntityRecord(
            source_key="tool:github-api",
            entity_type="tool",
            name="GitHub API",
            description="The NPM package description explicitly identifies the GitHub API as the integration target.",
            url="https://api.github.com/",
            categories=["Tools"],
            source_name=self.name,
            source_url=source_url,
            raw={"observed_name": "GitHub API", "role": "integration_target"},
            metadata={"tool": {"derived_role": "integration_target", "task_mapping_allowed": False}},
            fetched_at=fetched_at,
        )

    def _is_recent_package_release(self, published_at: object) -> bool:
        if not isinstance(published_at, str) or not published_at.strip():
            return False
        try:
            observed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return observed >= datetime(2025, 1, 1, tzinfo=timezone.utc)
