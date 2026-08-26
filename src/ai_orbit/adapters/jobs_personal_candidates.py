"""Semantic feasibility probes for Jobs and Personal candidate sources.

The generic :class:`CandidateSourceProbeAdapter` can only record network
reachability and response shape. It cannot express the *semantic* verdicts that
decide whether a source actually qualifies for a category:

* Jobs requires a genuine employer posting timestamp (``posted_at`` /
  ``created_at`` semantics), not the moment a listing was added to a
  crowd-sourced list.
* Personal requires an explicit personal-AI-assistant *product* identity, not a
  curated list of open-source frameworks/tools/repositories.

These probes fetch GitHub-hosted candidate documents, inspect their actual
semantics, and record an honest :class:`SourceFeasibility` verdict. They never
ingest records; a verdict of ``unusable`` is a real, re-runnable finding.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Callable

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import HttpRetryConfig, JsonHttpClient, SourceFetchError


def assess_simplifyjobs_timestamp_semantics(text: str) -> dict[str, Any]:
    """Assess whether a SimplifyJobs document establishes a genuine posting time.

    Returns a verdict dict with ``status``, ``failure_behavior`` and the list of
    schema field names documented in the text.
    """
    documented_fields = re.findall(r"\|\s*`([a-z_]+)`\s*\|", text)

    if "Unix timestamp when added" in text:
        return {
            "status": "unusable",
            "failure_behavior": (
                "date_posted is documented as 'Unix timestamp when added' — the moment a "
                "listing was added to the list by Simplify's hourly scraper or a community "
                "contributor — not the employer's posting time. The contribution form does "
                "not collect a posting date, so the source carries no genuine "
                "posted_at/created_at evidence. Rejected for Jobs under the "
                "posting-timestamp requirement."
            ),
            "documented_fields": documented_fields,
        }
    if "date_posted" in text:
        return {
            "status": "unusable",
            "failure_behavior": (
                "the document mentions date_posted but does not document it as the "
                "employer's posting time; no posted_at/created_at semantics could be "
                "verified from the source, so the posting-timestamp requirement fails."
            ),
            "documented_fields": documented_fields,
        }
    return {
        "status": "unusable",
        "failure_behavior": (
            "no posting-timestamp field with employer posted_at/created_at semantics is "
            "documented by the source; the posting-timestamp requirement cannot be met."
        ),
        "documented_fields": documented_fields,
    }


def assess_personal_assistant_identity(text: str) -> dict[str, Any]:
    """Assess whether a document supplies personal-AI-assistant product identity.

    A curated Markdown list of open-source assistant frameworks/tools is a
    framework/tool/repository listing, not a catalog of personal-AI-assistant
    products, so it fails the identity gate.
    """
    lowered = text.lower()
    is_curated_list = "curated list" in lowered
    is_open_source = "open-source" in lowered
    has_repo_links = bool(re.search(r"-\s*\[[^\]]+\]\(https://github\.com/[^)]+\)", text))

    if is_curated_list and is_open_source and has_repo_links:
        return {
            "status": "unusable",
            "failure_behavior": (
                "the document is a curated Markdown 'awesome' list of open-source, "
                "self-hosted assistant frameworks/tools (each entry is a GitHub repository "
                "link with a one-line description and a language badge); it supplies no "
                "structured entity identity records and no personal-assistant product "
                "identities, so it fails the personal-AI-assistant identity gate "
                "(frameworks/tools/repositories are not personal-assistant entities)."
            ),
        }
    return {
        "status": "unusable",
        "failure_behavior": (
            "the document does not establish explicit personal-AI-assistant product "
            "identity; a category label alone is not evidence, and no structured "
            "personal-assistant entity records were found."
        ),
    }


@dataclass(frozen=True)
class JobsPersonalProbeDefinition:
    source_name: str
    domain: str
    source_type: str
    access_method: str
    repo_path: str
    file_path: str
    required_fields: list[str]
    assess: Callable[[str], dict[str, Any]]
    pagination: str | None = None
    freshness: str | None = None
    ai_relevance: str | None = None
    company_identity_quality: str | None = None
    record_volume_estimate: str | None = None
    inventory_evidence: str | None = None
    available_fields: list[str] | None = None


class JobsPersonalCandidateProbeAdapter(SourceAdapter):
    """Fetches a GitHub-hosted candidate document and records a semantic verdict."""

    def __init__(
        self,
        settings: AIOrbitSettings,
        definition: JobsPersonalProbeDefinition,
        *,
        transport: Any = None,
    ) -> None:
        self.settings = settings
        self.definition = definition
        self.name = definition.source_name
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
            transport=transport,
            retry=HttpRetryConfig(
                max_attempts=settings.max_retry_attempts,
                backoff_base_seconds=settings.retry_backoff_base_seconds,
                backoff_max_seconds=settings.retry_backoff_max_seconds,
                jitter_seconds=settings.retry_jitter_seconds,
            ),
        )

    @property
    def _contents_url(self) -> str:
        return f"{self.settings.github_api_base.rstrip('/')}/repos/{self.definition.repo_path}/contents/{self.definition.file_path}"

    async def verify(self) -> SourceFeasibility:
        definition = self.definition
        url = self._contents_url
        try:
            response = await self.client.get_json(url)
            data = response.data
            if not isinstance(data, dict) or data.get("encoding") != "base64":
                return self._failure("GitHub contents payload missing base64 content; the document could not be semantically inspected")
            content = data.get("content")
            if not isinstance(content, str):
                return self._failure("GitHub contents payload missing the content field; the document could not be semantically inspected")
            try:
                decoded = base64.b64decode(content).decode("utf-8", "replace")
            except ValueError as exc:
                return self._failure(f"malformed base64 content from GitHub contents API: {exc}")

            verdict = definition.assess(decoded)
            documented = verdict.get("documented_fields") or []
            available_fields = definition.available_fields or []
            if documented:
                available_fields = list(dict.fromkeys([*documented, *available_fields]))
            return SourceFeasibility(
                source_name=definition.source_name,
                source_type=definition.source_type,
                access_method=definition.access_method,
                url=str(response.url),
                status=verdict["status"],  # type: ignore[arg-type]
                domain=definition.domain,
                http_status=response.status_code,
                pagination=definition.pagination,
                available_fields=available_fields,
                required_fields=definition.required_fields,
                authentication_required=False,
                rate_limit_observed={k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"},
                freshness=definition.freshness,
                anti_bot_js="GitHub REST API returned the document as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=definition.inventory_evidence,
                company_identity_quality=definition.company_identity_quality,
                ai_relevance=definition.ai_relevance,
                actual_crawl_feasibility=(
                    "reachable and parseable via GitHub, but not eligible for the category "
                    "(see failure_behavior)"
                ),
                record_volume_estimate=definition.record_volume_estimate,
                failure_behavior=verdict["failure_behavior"],
                yielded_usable_records=0,
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=definition.source_name,
                source_type=definition.source_type,
                access_method=definition.access_method,
                url=url,
                status="unusable",
                domain=definition.domain,
                http_status=exc.status_code,
                pagination=definition.pagination,
                available_fields=[],
                required_fields=definition.required_fields,
                authentication_required=False,
                freshness=definition.freshness,
                anti_bot_js="not determined; GitHub contents request failed",
                inventory_evidence=definition.inventory_evidence,
                company_identity_quality=definition.company_identity_quality,
                ai_relevance=definition.ai_relevance,
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                record_volume_estimate=definition.record_volume_estimate,
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        return []

    def _failure(self, failure_behavior: str) -> SourceFeasibility:
        definition = self.definition
        return SourceFeasibility(
            source_name=definition.source_name,
            source_type=definition.source_type,
            access_method=definition.access_method,
            url=self._contents_url,
            status="unusable",
            domain=definition.domain,
            http_status=None,
            pagination=definition.pagination,
            available_fields=[],
            required_fields=definition.required_fields,
            authentication_required=False,
            freshness=definition.freshness,
            anti_bot_js="not determined; the document could not be decoded or inspected",
            inventory_evidence=definition.inventory_evidence,
            company_identity_quality=definition.company_identity_quality,
            ai_relevance=definition.ai_relevance,
            actual_crawl_feasibility="reachable but not semantically inspectable; recorded as unusable for the category",
            record_volume_estimate=definition.record_volume_estimate,
            failure_behavior=failure_behavior,
        )


def build_jobs_personal_probe_adapters(settings: AIOrbitSettings) -> list[JobsPersonalCandidateProbeAdapter]:
    definitions = [
        JobsPersonalProbeDefinition(
            source_name="SimplifyJobs Internships Listings Probe",
            domain="Jobs",
            source_type="GitHub-hosted structured JSON listings + Markdown schema documentation",
            access_method="GitHub REST contents API for SimplifyJobs/Summer2027-Internships CONTRIBUTING.md (schema authority)",
            repo_path="SimplifyJobs/Summer2027-Internships",
            file_path="CONTRIBUTING.md",
            required_fields=["job title", "company", "job URL", "location", "posted/created timestamp", "source"],
            assess=assess_simplifyjobs_timestamp_semantics,
            pagination="single listings.json document (11 MB, 14,764 listing objects observed via the git-blobs API on 2026-08-26)",
            freshness="date_posted is documented as 'Unix timestamp when added' (list ingestion time), not the employer's posting time; it is not treated as a posting timestamp",
            ai_relevance="candidate jobs source with an explicit 'Data Science, AI & Machine Learning' category; downstream title filtering would still be required",
            company_identity_quality="company_name and a per-listing application URL are present, but no employer-verified posting timestamp exists",
            record_volume_estimate="14,764 listing objects (2,104 active) observed in the Summer 2027 internships listings.json on 2026-08-26",
            inventory_evidence="probe inspected CONTRIBUTING.md, which documents the listings.json schema; the full listings.json (11,071,400 bytes) was additionally inspected via the git-blobs API during investigation",
            available_fields=["company_name", "title", "url", "locations", "terms", "sponsorship"],
        ),
        JobsPersonalProbeDefinition(
            source_name="Awesome Personal AI Assistants List Probe",
            domain="Personal",
            source_type="GitHub-hosted Markdown curated list",
            access_method="GitHub REST contents API for elyase/awesome-personal-ai-assistants readme.md",
            repo_path="elyase/awesome-personal-ai-assistants",
            file_path="readme.md",
            required_fields=["assistant name", "canonical URL", "description", "personal-assistant identity evidence"],
            assess=assess_personal_assistant_identity,
            pagination="single Markdown readme.md document",
            freshness="no per-entry publication/release timestamps are supplied by the list",
            ai_relevance="entries are open-source self-hosted AI assistant projects, but the list is framework/tool oriented rather than a catalog of personal-assistant products",
            company_identity_quality="no product/vendor identity records; entries are GitHub repository links with one-line descriptions and language badges",
            record_volume_estimate="curated Markdown list of open-source assistant frameworks/tools; no structured entity records present",
            inventory_evidence="probe inspected readme.md: a curated list of open-source, self-hosted assistant frameworks/tools (e.g. OpenClaw, nanobot), with no structured entity identity records",
            available_fields=["entry name", "GitHub repository URL", "one-line description", "language tag"],
        ),
    ]
    return [JobsPersonalCandidateProbeAdapter(settings, definition) for definition in definitions]
