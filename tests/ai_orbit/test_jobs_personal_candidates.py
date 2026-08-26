"""Regression tests for the Jobs and Personal semantic feasibility probes.

These encode the two category gates found during investigation:

* Jobs: a crowd-sourced listing's ``date_posted`` is documented as "Unix
  timestamp when added" (list ingestion time), not the employer's posting time,
  so it must be rejected as posting-time evidence.
* Personal: a curated "awesome" list of open-source assistant
  frameworks/tools/repositories does not establish personal-AI-assistant
  product identity, so it must be rejected.
"""

import base64
import json

import httpx
import pytest

from src.ai_orbit.adapters.jobs_personal_candidates import (
    JobsPersonalCandidateProbeAdapter,
    assess_personal_assistant_identity,
    assess_simplifyjobs_timestamp_semantics,
    build_jobs_personal_probe_adapters,
)
from src.ai_orbit.config import AIOrbitSettings


_SIMPLIFYJOBS_SCHEMA = """\
## listings.json Schema

All internships are stored in `.github/scripts/listings.json`. A listing entry looks like:

| Field | Type | Description |
| --- | --- | --- |
| `source` | `str` | Which source added the listing |
| `company_name` | `str` | Company name |
| `title` | `str` | Job title |
| `url` | `str` | Link to job posting |
| `locations` | `list` | Job locations |
| `date_posted` | `int` | Unix timestamp when added |
| `date_updated` | `int` | Unix timestamp when last updated |
| `terms` | `list` | Terms offered (Summer 2027, etc.) |
| `sponsorship` | `str` | Sponsorship status |
"""


_AWESOME_PERSONAL_LIST = """\
# Awesome Personal AI Assistants

> A curated list of open-source personal AI assistants you run on your own devices.

- [OpenClaw](https://github.com/openclaw/openclaw) - The original personal AI assistant. `Node.js`
- [nanobot](https://github.com/HKUDS/nanobot) - Ultra-lightweight assistant in ~4,000 lines of Python. `Python`
"""


def test_jobs_timestamp_semantics_rejects_when_added() -> None:
    verdict = assess_simplifyjobs_timestamp_semantics(_SIMPLIFYJOBS_SCHEMA)
    assert verdict["status"] == "unusable"
    assert "when added" in verdict["failure_behavior"]
    assert "not the employer's posting time" in verdict["failure_behavior"]
    assert "date_posted" in verdict["documented_fields"]


def test_jobs_timestamp_semantics_extracts_documented_fields() -> None:
    verdict = assess_simplifyjobs_timestamp_semantics(_SIMPLIFYJOBS_SCHEMA)
    for field in ("company_name", "title", "url", "locations", "date_posted", "date_updated"):
        assert field in verdict["documented_fields"]


def test_jobs_timestamp_semantics_rejects_undocumented_posting_time() -> None:
    verdict = assess_simplifyjobs_timestamp_semantics("some schema doc mentioning date_posted without semantics")
    assert verdict["status"] == "unusable"
    assert "posted_at/created_at semantics" in verdict["failure_behavior"]


def test_personal_identity_gate_rejects_framework_tool_list() -> None:
    verdict = assess_personal_assistant_identity(_AWESOME_PERSONAL_LIST)
    assert verdict["status"] == "unusable"
    assert "frameworks/tools" in verdict["failure_behavior"]
    assert "identity gate" in verdict["failure_behavior"]


def test_personal_identity_gate_rejects_non_product_document() -> None:
    verdict = assess_personal_assistant_identity("A plain document with no assistant product identities.")
    assert verdict["status"] == "unusable"
    assert "identity" in verdict["failure_behavior"]


def _contents_response(text: str, path: str) -> httpx.Response:
    payload = {
        "name": path,
        "path": path,
        "encoding": "base64",
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }
    return httpx.Response(200, json=payload)


@pytest.mark.asyncio
async def test_probe_adapter_records_unusable_verdict_for_jobs() -> None:
    settings = AIOrbitSettings(log_level="CRITICAL")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "SimplifyJobs/Summer2027-Internships" in request.url.path
        return _contents_response(_SIMPLIFYJOBS_SCHEMA, "CONTRIBUTING.md")

    adapter = JobsPersonalCandidateProbeAdapter(
        settings,
        next(d for d in build_jobs_personal_probe_adapters(settings) if d.definition.domain == "Jobs").definition,
        transport=httpx.MockTransport(handler),
    )
    feasibility = await adapter.verify()
    assert feasibility.status == "unusable"
    assert feasibility.domain == "Jobs"
    assert feasibility.http_status == 200
    assert "when added" in feasibility.failure_behavior
    assert feasibility.yielded_usable_records == 0
    assert "date_posted" in feasibility.available_fields


@pytest.mark.asyncio
async def test_probe_adapter_records_unusable_verdict_for_personal() -> None:
    settings = AIOrbitSettings(log_level="CRITICAL")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "elyase/awesome-personal-ai-assistants" in request.url.path
        return _contents_response(_AWESOME_PERSONAL_LIST, "readme.md")

    adapter = JobsPersonalCandidateProbeAdapter(
        settings,
        next(d for d in build_jobs_personal_probe_adapters(settings) if d.definition.domain == "Personal").definition,
        transport=httpx.MockTransport(handler),
    )
    feasibility = await adapter.verify()
    assert feasibility.status == "unusable"
    assert feasibility.domain == "Personal"
    assert "identity gate" in feasibility.failure_behavior


@pytest.mark.asyncio
async def test_probe_adapter_never_ingests_records() -> None:
    settings = AIOrbitSettings(log_level="CRITICAL")
    adapter = build_jobs_personal_probe_adapters(settings)[0]
    assert await adapter.discover() == []


@pytest.mark.asyncio
async def test_probe_adapter_reports_network_failure() -> None:
    settings = AIOrbitSettings(log_level="CRITICAL", max_retry_attempts=1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    adapter = JobsPersonalCandidateProbeAdapter(
        settings,
        next(d for d in build_jobs_personal_probe_adapters(settings) if d.definition.domain == "Jobs").definition,
        transport=httpx.MockTransport(handler),
    )
    feasibility = await adapter.verify()
    assert feasibility.status == "unusable"
    assert feasibility.http_status == 404


@pytest.mark.asyncio
async def test_probe_adapter_handles_non_base64_payload() -> None:
    settings = AIOrbitSettings(log_level="CRITICAL")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"encoding": "none", "content": "raw"})

    adapter = JobsPersonalCandidateProbeAdapter(
        settings,
        next(d for d in build_jobs_personal_probe_adapters(settings) if d.definition.domain == "Personal").definition,
        transport=httpx.MockTransport(handler),
    )
    feasibility = await adapter.verify()
    assert feasibility.status == "unusable"
    assert "base64" in feasibility.failure_behavior
