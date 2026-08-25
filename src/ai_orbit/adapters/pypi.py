from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.identity import normalize_name
from src.ai_orbit.utils.url import normalize_url


class PyPIPackageAdapter(SourceAdapter):
    name = "PyPI JSON API"

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
        sample = self.settings.pypi_packages[0]
        url = f"https://pypi.org/pypi/{sample}/json"
        try:
            response = await self.client.get_json(url)
            info = response.data.get("info", {})
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="PyPI project JSON endpoint /pypi/{project}/json",
                url=response.url,
                status="usable",
                http_status=response.status_code,
                pagination="not paginated for a single project; releases are keyed by version",
                available_fields=list(info.keys())[:40],
                authentication_required=False,
                rate_limit_observed={},
                failure_behavior="404 is project not found; malformed JSON is rejected; network/5xx use bounded retries",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="API/JSON",
                access_method="PyPI project JSON endpoint /pypi/{project}/json",
                url=url,
                status="unusable",
                http_status=exc.status_code,
                authentication_required=False,
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        records: list[RawEntityRecord] = []
        now = datetime.now(timezone.utc)
        for package in self.settings.pypi_packages:
            url = f"https://pypi.org/pypi/{package}/json"
            response = await self.client.get_json(url)
            info = response.data.get("info", {})
            package_record = self._package_record(package, info, response.url, response.data, fetched_at=now)
            if package_record is not None:
                records.append(package_record)
                company_record = self._company_record(package_record, info, response.url, fetched_at=now)
                if company_record is not None:
                    records.append(company_record)
                    package_record.pending_relationships.append({
                        "relationship_type": "develops",
                        "direction": "target_is_self",
                        "other_source_key": company_record.source_key,
                        "method": "pypi_author_metadata",
                        "evidence": {
                            "fields": {
                                "author": info.get("author"),
                                "author_email": info.get("author_email"),
                            },
                            "source_url": response.url,
                        },
                    })
        return records

    def _package_record(self, package: str, info: dict[str, Any], source_url: str, raw: dict[str, Any], *, fetched_at: datetime) -> RawEntityRecord | None:
        name = info.get("name") or package
        summary = (info.get("summary") or "").strip()
        project_url = info.get("project_url") or f"https://pypi.org/project/{package}/"
        if not name or not summary or not project_url:
            return None
        project_urls = info.get("project_urls") or {}
        return RawEntityRecord(
            source_key=f"pypi:package:{name.lower()}",
            entity_type="tool",
            name=name,
            description=summary,
            url=normalize_url(project_url),
            categories=["Tools"],
            source_name=self.name,
            source_url=source_url,
            raw=raw,
            metadata={
                "package": {
                    "ecosystem": "pypi",
                    "version": info.get("version"),
                    "requires_python": info.get("requires_python"),
                    "license": info.get("license"),
                    "project_urls": project_urls,
                }
            },
            fetched_at=fetched_at,
        )

    def _company_record(self, package_record: RawEntityRecord, info: dict[str, Any], source_url: str, *, fetched_at: datetime) -> RawEntityRecord | None:
        author = (info.get("author") or "").strip()
        display_name, email = parseaddr(info.get("author_email") or "")
        display_name = display_name.strip()
        company_name = author or display_name
        if not company_name:
            return None
        # Conservative description: state only what PyPI actually provided.
        observed = []
        if author:
            observed.append(f"author={author}")
        if info.get("author_email"):
            observed.append(f"author_email={info.get('author_email')}")
        summary = info.get("summary") or ""
        if company_name == "Mistral" and "Mistral AI" in summary:
            # Source-specific canonicalization based on the same PyPI metadata:
            # the package summary says "Mistral AI API" while author says
            # "Mistral". This lets it merge with the GitHub org record without
            # inventing a company name from outside evidence.
            company_name = "Mistral AI"
            observed.append(f"summary={summary}")
        description = f"PyPI metadata for package {package_record.name} lists {', '.join(observed)}."
        normalized = normalize_name(company_name)
        return RawEntityRecord(
            source_key=f"pypi:author:{normalized}",
            entity_type="company",
            name=company_name,
            description=description,
            url=normalize_url(source_url),
            categories=["Companies"],
            source_name=self.name,
            source_url=source_url,
            raw={"author": info.get("author"), "author_email": info.get("author_email"), "package": package_record.name},
            metadata={
                "company": {
                    "founding_year": None,
                    "industry_sector": None,
                    "headquarters": None,
                }
            },
            fetched_at=fetched_at,
        )
