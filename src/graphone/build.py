"""Build the separate, source-backed GraphOne trial artifacts.

The GraphOne trial is intentionally independent of the AI Orbit entity graph.
It preserves the existing 1,000-paper arXiv export, uses a documented public
YC-directory snapshot for startup records, uses a documented AI product
-directory for product records, and accepts News only when GitHub exposes its
actual release ``published_at`` timestamp.  Jobs are never synthesized: an
empty tab is written when the accessible sources cannot prove an employer
posting timestamp.

All network retrieval is completed before any committed artifact is replaced.
A source-reachability failure therefore cannot silently replace a verified
output with a degraded one.
"""
from __future__ import annotations

import argparse
import base64
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "graphone"
RESEARCH_PAPERS_INPUT = (
    PROJECT_ROOT
    / "ResearchPaperSpreadsheetsAvailableForOfflineView"
    / "GraphOneSliceResearchPapers(FirstOneThousandEntries).csv"
)

GITHUB_API_BASE = "https://api.github.com"

# These immutable Git blob IDs and commit URLs are the exact source snapshots
# used for the final startup/product export.  Pinning removes ambiguity when a
# third-party directory later changes and lets a reviewer retrieve the exact
# evidence file through GitHub's public API.
YC_VAULT_SOURCE = {
    "source_name": "YC Vault public YC Directory snapshot",
    "repository": "lukaflpvc/YC-Vault",
    "commit": "1c86f32a981d479249496298f6bb746ff3c79efe",
    "snapshot_date": "2025-04-21",
    "path": "data/2025-04-21/YC_Companies.csv",
    "blob_sha": "cda06c1570edf61b4e2200b5cc1de53fed4376ad",
    "readme_url": "https://github.com/lukaflpvc/YC-Vault/blob/1c86f32a981d479249496298f6bb746ff3c79efe/README.md",
}
AI_TOOLS_LIST_SOURCE = {
    "source_name": "AI Tools List Product Directory",
    "repository": "lakey009/AI-Tools-List",
    "commit": "ccdff902d7e77774df46e66761e811ada4838ea1",
    "path": "AIToolsList.json",
    "blob_sha": "208576ae39b4cf1f4a96e448378b7582dc679559",
}

# These repositories are deliberately a small, reviewable allowlist of AI
# projects rather than a global GitHub scrape.  AI relevance is checked again
# against the observed repository description/topics before any release is
# accepted into the News output.
NEWS_REPOSITORIES = (
    "huggingface/transformers",
    "huggingface/diffusers",
    "huggingface/datasets",
    "huggingface/peft",
    "huggingface/accelerate",
    "cohere-ai/cohere-python",
    "groq/groq-python",
    "mistralai/client-python",
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "modelcontextprotocol/typescript-sdk",
    "langchain-ai/langchain",
    "langchain-ai/langgraph",
    "run-llama/llama_index",
    "vllm-project/vllm",
    "ollama/ollama",
    "Comfy-Org/ComfyUI",
    "microsoft/semantic-kernel",
    "microsoft/autogen",
    "deepset-ai/haystack",
    "milvus-io/milvus",
    "qdrant/qdrant",
    "chroma-core/chroma",
    "weaviate/weaviate",
    "BentoML/BentoML",
    "gradio-app/gradio",
    "mlflow/mlflow",
    "pytorch/pytorch",
    "tensorflow/tensorflow",
    "scikit-learn/scikit-learn",
    "black-forest-labs/flux",
    "stability-ai/stablediffusion",
)

STARTUP_LIMIT = 1000
PRODUCT_LIMIT = 1000
NEWS_LOOKBACK = timedelta(hours=24)

STARTUP_COLUMNS = [
    "id",
    "canonical_name",
    "canonical_url",
    "employee_count",
    "yc_batch",
    "industry",
    "location",
    "status",
    "source_url",
    "source_record_id",
    "collectedAt",
]
PRODUCT_COLUMNS = [
    "id",
    "product_name",
    "product_url",
    "description",
    "provider",
    "pricing_model",
    "source_url",
    "source_record_id",
    "collectedAt",
]
RESEARCH_COLUMNS = [
    "id",
    "schemaVersion",
    "recordType",
    "source_name",
    "source_url",
    "title",
    "authors",
    "paper_url",
    "github_url",
    "github_stars",
    "published_date",
    "collectedAt",
    "github_stars_fetched_at",
    "github_evidence_type",
]
JOB_COLUMNS = [
    "id",
    "company",
    "title",
    "url",
    "location",
    "posted_at",
    "remote_status",
    "role_family",
    "source",
    "source_url",
    "collectedAt",
]
NEWS_COLUMNS = [
    "id",
    "title",
    "canonical_url",
    "publisher",
    "published_at",
    "timestamp_semantics",
    "repository",
    "ai_relevance",
    "source_url",
    "collectedAt",
]
MAPPING_COLUMNS = [
    "record_type",
    "raw_source_key",
    "raw_value",
    "canonical_id",
    "canonical_value",
    "method",
    "confidence",
    "source_url",
    "reason",
]

AI_PRODUCT_TERMS = {
    "ai",
    "chatgpt",
    "gpt",
    "llm",
    "machine learning",
    "generative",
    "stable diffusion",
}
NON_PRODUCT_DESCRIPTION_PATTERNS = (
    re.compile(r"^\s*(?:a\s+)?guide\b", re.I),
    re.compile(r"\bguide\s+to\b", re.I),
    re.compile(r"\b(?:article|blog|newsletter|tutorial|course)\b", re.I),
    re.compile(r"\bdevelops\s+(?:open-source\s+)?ai\s+models\b", re.I),
)
SHORT_AI_SIGNALS = ("ai", "gpt", "llm", "nlp", "mcp")
LONG_AI_SIGNALS = (
    "artificial-intelligence",
    "artificial intelligence",
    "machine-learning",
    "machine learning",
    "deep-learning",
    "deep learning",
    "generative",
    "transformer",
    "diffusion",
    "stable-diffusion",
    "stable diffusion",
    "openai",
    "open ai",
    "anthropic",
    "cohere",
    "groq",
    "mistral",
    "huggingface",
    "hugging face",
    "model-context-protocol",
    "model context protocol",
    "chatgpt",
    "chatbot",
    "multimodal",
    "neural",
    "embedding",
    "natural-language",
    "computer-vision",
    "speech-recognition",
    "reinforcement-learning",
)


class GraphOneBuildError(RuntimeError):
    """Base exception for a build that intentionally writes no outputs."""


class SourceFetchFailure(GraphOneBuildError):
    """A required source was unavailable or did not match its pinned blob."""


class GraphOneValidationError(GraphOneBuildError):
    """Generated records did not meet the trial's explicit quality gates."""


@dataclass(frozen=True)
class GitHubFetcher:
    """Minimal JSON client for public GitHub REST artifacts.

    A token is used when the runtime provides one, but no token is embedded in
    the repository or written to artifacts/logs.
    """

    token: str | None = None
    timeout_seconds: float = 30.0

    def get_json(self, url: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "GraphOneSlice-GraphOne-Final/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - fixed HTTPS sources
                body = response.read()
        except HTTPError as exc:
            raise SourceFetchFailure(f"HTTP {exc.code} retrieving {url}") from exc
        except URLError as exc:
            raise SourceFetchFailure(f"network failure retrieving {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SourceFetchFailure(f"timeout retrieving {url}") from exc
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceFetchFailure(f"malformed JSON from {url}") from exc

    def get_blob_text(self, repository: str, blob_sha: str) -> str:
        url = f"{GITHUB_API_BASE}/repos/{repository}/git/blobs/{blob_sha}"
        payload = self.get_json(url)
        if not isinstance(payload, dict):
            raise SourceFetchFailure(f"unexpected Git blob payload from {url}")
        if payload.get("sha") != blob_sha or payload.get("encoding") != "base64":
            raise SourceFetchFailure(f"Git blob identity/encoding mismatch for {url}")
        content = payload.get("content")
        if not isinstance(content, str):
            raise SourceFetchFailure(f"Git blob content absent for {url}")
        try:
            return base64.b64decode(content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceFetchFailure(f"Git blob base64 decode failed for {url}") from exc


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _nullable_source_text(value: Any) -> str | None:
    value = _clean_text(value)
    return None if not value or value.casefold() in {"none", "null", "n/a", "unknown"} else value


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _product_dedupe_key(value: str) -> str:
    normalized = _normalize_url(value)
    parsed = urlsplit(normalized)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))


def _stable_id(record_type: str, identity: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"graphone:{record_type}:{identity}"))


def _blob_url(source: dict[str, str]) -> str:
    return f"https://github.com/{source['repository']}/blob/{source['commit']}/{source['path']}"


def _blob_api_url(source: dict[str, str]) -> str:
    return f"{GITHUB_API_BASE}/repos/{source['repository']}/git/blobs/{source['blob_sha']}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ai_product_evidence(description: str) -> dict[str, Any] | None:
    normalized = f" {re.sub(r'[^a-z0-9]+', ' ', description.lower()).strip()} "
    signals = sorted(term for term in AI_PRODUCT_TERMS if f" {term} " in normalized)
    if re.search(r"\bgpt[- ]?\d", description, flags=re.I):
        signals.append("gpt identifier")
    if not signals:
        return None
    return {
        "field": "description",
        "signals": sorted(set(signals)),
        "excerpt": description[:240],
    }


def _product_rejection_reason(row: Any) -> str | None:
    if not isinstance(row, dict):
        return "non_object_record"
    if not _clean_text(row.get("handle")):
        return "missing_product_name"
    website = row.get("website")
    if not isinstance(website, str) or not _is_http_url(website):
        return "missing_or_invalid_product_url"
    description = row.get("description")
    if not isinstance(description, str) or not _clean_text(description):
        return "missing_description"
    if any(pattern.search(description) for pattern in NON_PRODUCT_DESCRIPTION_PATTERNS):
        return "non_product_semantics"
    if _ai_product_evidence(description) is None:
        return "missing_explicit_ai_evidence"
    return None


def _ai_signal_tokens(text: str) -> list[str]:
    lowered = _clean_text(text).lower()
    matched: list[str] = []
    for token in SHORT_AI_SIGNALS:
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
            matched.append(token)
    for token in LONG_AI_SIGNALS:
        if token in lowered:
            matched.append(token)
    return matched


def _news_ai_evidence(repository: dict[str, Any]) -> dict[str, Any] | None:
    observed_fields = {
        "repository.description": _clean_text(repository.get("description")),
        "repository.topics": " ".join(str(item) for item in repository.get("topics", []) if item),
        "repository.full_name": _clean_text(repository.get("full_name")),
    }
    matched_fields: dict[str, list[str]] = {}
    for field, text in observed_fields.items():
        tokens = _ai_signal_tokens(text)
        if tokens:
            matched_fields[field] = tokens
    if not matched_fields:
        return None
    matched_tokens: list[str] = []
    for tokens in matched_fields.values():
        for token in tokens:
            if token not in matched_tokens:
                matched_tokens.append(token)
    return {
        "matched_fields": sorted(matched_fields),
        "matched_tokens": matched_tokens,
        "excerpt": observed_fields["repository.description"][:240]
        or observed_fields["repository.full_name"],
    }


def _clean_release_body(value: Any, *, limit: int = 800) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*_`'\"|]", " ", text)
    return _clean_text(text)[:limit]


def build_startups(
    fetcher: GitHubFetcher,
    *,
    collected_at: datetime,
    limit: int = STARTUP_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Create active startup records from a pinned public YC directory snapshot.

    The input snapshot has no stable company identifier.  It contains known
    homonyms (same display name for different YC batches), so name-only entity
    resolution would be unsafe.  The output therefore preserves the exact
    source-row identity rather than falsely merging similarly named companies.
    """

    csv_text = fetcher.get_blob_text(YC_VAULT_SOURCE["repository"], YC_VAULT_SOURCE["blob_sha"])
    rows = list(csv.DictReader(csv_text.splitlines()))
    expected_fields = {"Name", "Batch", "Status", "Industry", "Team Size", "Location"}
    if not rows or not expected_fields.issubset(rows[0]):
        raise SourceFetchFailure("YC Vault snapshot did not contain the documented company-profile columns")

    source_file_url = _blob_url(YC_VAULT_SOURCE)
    rejected = Counter()
    candidates: list[tuple[int, dict[str, Any], int]] = []
    for row_number, row in enumerate(rows, start=2):
        name = _clean_text(row.get("Name"))
        if not name:
            rejected["missing_company_name"] += 1
            continue
        if name.casefold() == "y combinator":
            # The accelerator is a directory entry, not a portfolio startup.
            rejected["accelerator_not_portfolio_startup"] += 1
            continue
        if _clean_text(row.get("Status")).casefold() != "active":
            rejected["not_active_in_source_snapshot"] += 1
            continue
        team_size_value = _nullable_source_text(row.get("Team Size"))
        if team_size_value is None or not re.fullmatch(r"\d+", team_size_value):
            rejected["missing_employee_count"] += 1
            continue
        employee_count = int(team_size_value)
        if employee_count <= 0:
            rejected["non_positive_employee_count"] += 1
            continue
        candidates.append((row_number, row, employee_count))

    accepted_candidates = candidates[:limit]
    records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for row_number, row, employee_count in accepted_candidates:
        name = _clean_text(row["Name"])
        source_record_id = f"yc-vault:2025-04-21:YC_Companies.csv:row:{row_number}"
        source_url = f"{source_file_url}#L{row_number}"
        record_id = _stable_id("startup", source_record_id)
        observed_fields = {
            "Name": name,
            "Batch": _nullable_source_text(row.get("Batch")),
            "Status": _clean_text(row.get("Status")),
            "Industry": _nullable_source_text(row.get("Industry")),
            "Team Size": employee_count,
            "Location": _nullable_source_text(row.get("Location")),
        }
        records.append(
            {
                "id": record_id,
                "recordType": "STARTUP",
                "canonical_name": name,
                # The snapshot does not map names to an authoritative company
                # URL in the same row, so no URL is inferred or positionally
                # joined from its separate YC_URLs.csv file.
                "canonical_url": None,
                "employee_count": employee_count,
                "employee_count_source_field": "Team Size",
                "yc_batch": observed_fields["Batch"],
                "industry": observed_fields["Industry"],
                "location": observed_fields["Location"],
                "status": "Active",
                "source_url": source_url,
                "source_record_id": source_record_id,
                "collectedAt": _iso(collected_at),
                "provenance": {
                    "source_name": YC_VAULT_SOURCE["source_name"],
                    "source_repository": YC_VAULT_SOURCE["repository"],
                    "source_commit": YC_VAULT_SOURCE["commit"],
                    "source_snapshot_date": YC_VAULT_SOURCE["snapshot_date"],
                    "source_file_url": source_file_url,
                    "source_blob_api_url": _blob_api_url(YC_VAULT_SOURCE),
                    "source_row_number": row_number,
                    "source_file_sha256": _sha256_text(csv_text),
                    "observed_fields": observed_fields,
                    "identity_evidence": (
                        "The source repository documents YC_Companies.csv as company profiles and metrics from "
                        "its YC Directory Database. This accepted source row is marked Active; its row identity is "
                        "preserved because no authoritative cross-row company ID is supplied."
                    ),
                    "metadata_semantics": (
                        "Team Size, industry, location, and status are observations from the dated secondary source "
                        "snapshot, not revalidated current facts."
                    ),
                },
            }
        )
        mappings.append(
            {
                "record_type": "startup",
                "raw_source_key": source_record_id,
                "raw_value": name,
                "canonical_id": record_id,
                "canonical_value": name,
                "method": "source_row_identity",
                "confidence": 1.0,
                "source_url": source_url,
                "reason": "No name-only merge: source-row identity prevents conflating documented startup homonyms.",
            }
        )

    metrics = {
        "source_name": YC_VAULT_SOURCE["source_name"],
        "source_snapshot_date": YC_VAULT_SOURCE["snapshot_date"],
        "source_input_rows": len(rows),
        "candidate_rows_after_quality_gates": len(candidates),
        "accepted_rows": len(records),
        "valid_rows_not_exported_due_target_limit": max(0, len(candidates) - len(records)),
        "rejected_by_reason": dict(sorted(rejected.items())),
        "employee_count_coverage": (len(records) / len(records)) if records else 0.0,
        "source_file_url": source_file_url,
        "source_blob_api_url": _blob_api_url(YC_VAULT_SOURCE),
    }
    if len(records) < limit:
        raise SourceFetchFailure(
            f"YC Vault snapshot yielded only {len(records)} source-backed active startup rows; required target is {limit}"
        )
    return records, mappings, metrics


def build_products(
    fetcher: GitHubFetcher,
    *,
    collected_at: datetime,
    limit: int = PRODUCT_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Create actual product/service records from a pinned product directory."""

    source_text = fetcher.get_blob_text(AI_TOOLS_LIST_SOURCE["repository"], AI_TOOLS_LIST_SOURCE["blob_sha"])
    try:
        source_rows = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise SourceFetchFailure("AI Tools List pinned blob was not JSON") from exc
    if not isinstance(source_rows, list):
        raise SourceFetchFailure("AI Tools List pinned blob was not a JSON array")

    source_file_url = _blob_url(AI_TOOLS_LIST_SOURCE)
    rejected = Counter()
    candidates: list[dict[str, Any]] = []
    seen_product_urls: set[str] = set()
    for row in source_rows:
        reason = _product_rejection_reason(row)
        if reason:
            rejected[reason] += 1
            continue
        assert isinstance(row, dict)
        normalized_url = _normalize_url(str(row["website"]))
        dedupe_key = _product_dedupe_key(normalized_url)
        if dedupe_key in seen_product_urls:
            rejected["duplicate_canonical_product_url"] += 1
            continue
        seen_product_urls.add(dedupe_key)
        candidates.append(row)

    accepted_candidates = candidates[:limit]
    records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for row in accepted_candidates:
        directory_id = row.get("id")
        name = _clean_text(row["handle"])
        product_url = _normalize_url(str(row["website"]))
        description = _clean_text(row["description"])
        evidence = _ai_product_evidence(description)
        assert evidence is not None
        source_record_id = f"ai-tools-list:AIToolsList.json:{directory_id}"
        record_id = _stable_id("product", _product_dedupe_key(product_url))
        records.append(
            {
                "id": record_id,
                "recordType": "PRODUCT",
                "product_name": name,
                "product_url": product_url,
                "description": description,
                # The directory does not state provider/company or pricing;
                # preserving nulls is intentional rather than an inference.
                "provider": None,
                "pricing_model": None,
                "source_url": source_file_url,
                "source_record_id": source_record_id,
                "collectedAt": _iso(collected_at),
                "provenance": {
                    "source_name": AI_TOOLS_LIST_SOURCE["source_name"],
                    "source_repository": AI_TOOLS_LIST_SOURCE["repository"],
                    "source_commit": AI_TOOLS_LIST_SOURCE["commit"],
                    "source_file_url": source_file_url,
                    "source_blob_api_url": _blob_api_url(AI_TOOLS_LIST_SOURCE),
                    "source_file_sha256": _sha256_text(source_text),
                    "source_record_id": directory_id,
                    "observed_fields": {
                        "id": directory_id,
                        "handle": name,
                        "website": row["website"],
                        "description": row["description"],
                    },
                    "product_identity_evidence": (
                        "The source is a directory of AI tools/products; this row supplies a product handle, website, "
                        "and description directly. Package, repository, model, feature, and editorial semantics are "
                        "rejected by the product quality gate."
                    ),
                    "ai_relevance_evidence": evidence,
                    "unknown_fields_preserved_as_null": ["provider", "pricing_model"],
                },
            }
        )
        mappings.append(
            {
                "record_type": "product",
                "raw_source_key": source_record_id,
                "raw_value": name,
                "canonical_id": record_id,
                "canonical_value": product_url,
                "method": "canonical_product_url",
                "confidence": 1.0,
                "source_url": source_file_url,
                "reason": "Unique normalized product URL after deterministic www/trailing-slash deduplication.",
            }
        )

    metrics = {
        "source_name": AI_TOOLS_LIST_SOURCE["source_name"],
        "source_input_rows": len(source_rows),
        "candidate_rows_after_quality_gates": len(candidates),
        "accepted_rows": len(records),
        "valid_rows_not_exported_due_target_limit": max(0, len(candidates) - len(records)),
        "rejected_by_reason": dict(sorted(rejected.items())),
        "provider_coverage": 0.0,
        "pricing_model_coverage": 0.0,
        "source_file_url": source_file_url,
        "source_blob_api_url": _blob_api_url(AI_TOOLS_LIST_SOURCE),
    }
    if len(records) < limit:
        raise SourceFetchFailure(
            f"AI Tools List yielded only {len(records)} source-backed product rows; required target is {limit}"
        )
    return records, mappings, metrics


def build_research_papers(
    *, collected_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Preserve and independently validate the existing 1,000-paper export."""

    if not RESEARCH_PAPERS_INPUT.is_file():
        raise SourceFetchFailure(f"preserved research-paper export is missing: {RESEARCH_PAPERS_INPUT}")
    with RESEARCH_PAPERS_INPUT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "schemaVersion",
        "recordType",
        "source_name",
        "source_url",
        "title",
        "authors",
        "paper_url",
        "published_date",
        "collectedAt",
    }
    if not rows or not required.issubset(rows[0]):
        raise SourceFetchFailure("preserved research-paper CSV lacks required GraphOne columns")

    records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        title = _clean_text(row.get("title"))
        paper_url = _clean_text(row.get("paper_url"))
        source_url = _clean_text(row.get("source_url"))
        published_at = _parse_timestamp(row.get("published_date"))
        if (
            row.get("recordType") != "RESEARCH_PAPER"
            or not title
            or not _is_http_url(paper_url)
            or not _is_http_url(source_url)
            or published_at is None
        ):
            rejected.append({"source_row_number": row_number, "reason": "required_research_fields_invalid"})
            continue
        record_id = _stable_id("research_paper", paper_url)
        record = {
            "id": record_id,
            "schemaVersion": row.get("schemaVersion") or "1.0",
            "recordType": "RESEARCH_PAPER",
            "source_name": row.get("source_name") or "arxiv",
            "source_url": source_url,
            "title": title,
            "authors": _clean_text(row.get("authors")),
            "paper_url": paper_url,
            "github_url": _nullable_source_text(row.get("github_url")),
            "github_stars": int(row["github_stars"]) if _nullable_source_text(row.get("github_stars")) else None,
            "published_date": _iso(published_at),
            "collectedAt": _clean_text(row.get("collectedAt")),
            "github_stars_fetched_at": _nullable_source_text(row.get("github_stars_fetched_at")),
            "github_evidence_type": _nullable_source_text(row.get("github_evidence_type")),
            "provenance": {
                "source_name": row.get("source_name") or "arxiv",
                "source_url": source_url,
                "source_csv": str(RESEARCH_PAPERS_INPUT.relative_to(PROJECT_ROOT)),
                "source_csv_row_number": row_number,
                "preservation_note": "Copied without re-ingesting arXiv; the existing validated 1,000-paper output remains the source of truth.",
                "graphone_packaged_at": _iso(collected_at),
            },
        }
        records.append(record)
        mappings.append(
            {
                "record_type": "research_paper",
                "raw_source_key": f"research-papers-csv:row:{row_number}",
                "raw_value": paper_url,
                "canonical_id": record_id,
                "canonical_value": paper_url,
                "method": "canonical_paper_url",
                "confidence": 1.0,
                "source_url": source_url,
                "reason": "arXiv canonical paper URL is the deterministic identity key.",
            }
        )

    if rejected:
        raise SourceFetchFailure(
            f"preserved research-paper export contains {len(rejected)} invalid rows; it was not copied over the last verified output"
        )
    metrics = {
        "source_name": "arXiv preserved research-paper export",
        "source_input_rows": len(rows),
        "accepted_rows": len(records),
        "rejected_by_reason": {},
        "unique_paper_urls": len({record["paper_url"] for record in records}),
        "source_csv": str(RESEARCH_PAPERS_INPUT.relative_to(PROJECT_ROOT)),
        "source_csv_sha256": hashlib.sha256(RESEARCH_PAPERS_INPUT.read_bytes()).hexdigest(),
    }
    if len(records) < 1000:
        raise SourceFetchFailure(f"preserved research-paper export has {len(records)} valid rows, below the 1,000 target")
    return records, mappings, metrics


def build_news(
    fetcher: GitHubFetcher,
    *,
    collected_at: datetime,
    repositories: Iterable[str] = NEWS_REPOSITORIES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Accept only fresh, timestamped GitHub release announcements as News."""

    cutoff = collected_at - NEWS_LOOKBACK
    candidates: list[dict[str, Any]] = []
    source_checks: list[dict[str, Any]] = []
    rejection_counts = Counter()
    repository_metadata_successes = 0
    release_fetch_successes = 0
    seen: set[str] = set()

    for repository_name in repositories:
        repository_api_url = f"{GITHUB_API_BASE}/repos/{repository_name}"
        try:
            repository = fetcher.get_json(repository_api_url)
        except SourceFetchFailure as exc:
            source_checks.append(
                {
                    "source_name": "GitHub REST repository API",
                    "repository": repository_name,
                    "url": repository_api_url,
                    "checked_at": _iso(collected_at),
                    "status": "unusable",
                    "reason": str(exc),
                }
            )
            continue
        if not isinstance(repository, dict) or not _clean_text(repository.get("full_name")):
            source_checks.append(
                {
                    "source_name": "GitHub REST repository API",
                    "repository": repository_name,
                    "url": repository_api_url,
                    "checked_at": _iso(collected_at),
                    "status": "unusable",
                    "reason": "repository payload lacked full_name",
                }
            )
            continue
        repository_metadata_successes += 1
        ai_evidence = _news_ai_evidence(repository)
        if ai_evidence is None:
            rejection_counts["repository_missing_observed_ai_relevance"] += 1
            source_checks.append(
                {
                    "source_name": "GitHub REST repository API",
                    "repository": repository_name,
                    "url": repository_api_url,
                    "checked_at": _iso(collected_at),
                    "status": "rejected",
                    "reason": "repository description/topics/full_name contained no accepted AI signal",
                }
            )
            continue

        release_list_api_url = f"{GITHUB_API_BASE}/repos/{repository_name}/releases?per_page=30"
        try:
            releases = fetcher.get_json(release_list_api_url)
        except SourceFetchFailure as exc:
            source_checks.append(
                {
                    "source_name": "GitHub REST Releases API",
                    "repository": repository_name,
                    "url": release_list_api_url,
                    "checked_at": _iso(collected_at),
                    "status": "unusable",
                    "reason": str(exc),
                }
            )
            continue
        if not isinstance(releases, list):
            source_checks.append(
                {
                    "source_name": "GitHub REST Releases API",
                    "repository": repository_name,
                    "url": release_list_api_url,
                    "checked_at": _iso(collected_at),
                    "status": "unusable",
                    "reason": "release-list payload was not an array",
                }
            )
            continue
        release_fetch_successes += 1
        source_checks.append(
            {
                "source_name": "GitHub REST Releases API",
                "repository": repository_name,
                "url": release_list_api_url,
                "checked_at": _iso(collected_at),
                "status": "usable",
                "records_examined": len(releases),
                "reason": "GitHub returns release published_at as a source publication timestamp.",
            }
        )

        for release in releases:
            if not isinstance(release, dict):
                rejection_counts["malformed_release_record"] += 1
                continue
            if release.get("draft") is True:
                rejection_counts["draft_release"] += 1
                continue
            if release.get("prerelease") is True:
                rejection_counts["prerelease_release"] += 1
                continue
            release_id = release.get("id")
            canonical_url = _clean_text(release.get("html_url"))
            source_url = _clean_text(release.get("url"))
            title = _clean_text(release.get("name")) or _clean_text(release.get("tag_name"))
            published_at = _parse_timestamp(release.get("published_at"))
            if not release_id or not title or not _is_http_url(canonical_url) or not _is_http_url(source_url) or published_at is None:
                rejection_counts["missing_required_release_fields"] += 1
                continue
            if published_at > collected_at:
                rejection_counts["future_publication_timestamp"] += 1
                continue
            if published_at < cutoff:
                rejection_counts["outside_24_hour_window"] += 1
                continue
            source_key = f"github-release:{repository['full_name'].casefold()}:{release_id}"
            if source_key in seen:
                rejection_counts["duplicate_release_identity"] += 1
                continue
            seen.add(source_key)
            owner = repository.get("owner") if isinstance(repository.get("owner"), dict) else {}
            record_id = _stable_id("news", source_key)
            candidates.append(
                {
                    "id": record_id,
                    "recordType": "NEWS",
                    "title": title,
                    "canonical_url": _normalize_url(canonical_url),
                    "description": _clean_release_body(release.get("body")),
                    "publisher": _clean_text(owner.get("login")) or None,
                    "publisher_type": _clean_text(owner.get("type")) or None,
                    "published_at": _iso(published_at),
                    "timestamp_semantics": "github_release_published_at",
                    "repository": _clean_text(repository.get("full_name")),
                    "release_id": release_id,
                    "tag_name": _clean_text(release.get("tag_name")) or None,
                    "ai_relevance": ai_evidence,
                    "source_url": source_url,
                    "source_record_id": source_key,
                    "collectedAt": _iso(collected_at),
                    "provenance": {
                        "source_name": "GitHub REST Releases API",
                        "release_api_url": source_url,
                        "repository_api_url": repository_api_url,
                        "repository": _clean_text(repository.get("full_name")),
                        "observed_published_at": release.get("published_at"),
                        "timestamp_semantics": (
                            "GitHub release published_at; it is not a crawl, retrieval, update, or commit timestamp."
                        ),
                        "publisher": {
                            "login": _clean_text(owner.get("login")) or None,
                            "type": _clean_text(owner.get("type")) or None,
                            "html_url": _clean_text(owner.get("html_url")) or None,
                        },
                        "ai_relevance_evidence": ai_evidence,
                    },
                }
            )

    if repository_metadata_successes == 0 or release_fetch_successes == 0:
        raise SourceFetchFailure(
            "GitHub release reachability collapsed before any usable source response; existing GraphOne outputs were preserved"
        )

    records = sorted(candidates, key=lambda item: (item["published_at"], item["id"]), reverse=True)
    mappings = [
        {
            "record_type": "news",
            "raw_source_key": record["source_record_id"],
            "raw_value": record["canonical_url"],
            "canonical_id": record["id"],
            "canonical_value": record["canonical_url"],
            "method": "github_release_identity",
            "confidence": 1.0,
            "source_url": record["source_url"],
            "reason": "Repository full name plus immutable GitHub release ID is the deterministic release identity.",
        }
        for record in records
    ]
    metrics = {
        "source_name": "GitHub REST Releases API",
        "repositories_configured": len(tuple(repositories)),
        "repository_metadata_successes": repository_metadata_successes,
        "release_source_successes": release_fetch_successes,
        "accepted_rows": len(records),
        "freshness_window_start": _iso(cutoff),
        "freshness_window_end": _iso(collected_at),
        "freshness_requirement": "published_at must be within the inclusive 24-hour window and use GitHub release publication semantics",
        "rejected_by_reason": dict(sorted(rejection_counts.items())),
    }
    return records, mappings, metrics, source_checks


def _probe_url(url: str, *, timeout_seconds: float = 15.0) -> tuple[bool, str]:
    """Probe a public job endpoint without treating response time as job data."""

    request = Request(url, headers={"User-Agent": "GraphOneSlice-GraphOne-Final/1.0", "Accept": "application/json, text/html;q=0.5"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS candidate endpoint
            response.read(1)
            return True, f"HTTP {response.status} reachable; no record accepted until employer posted_at semantics are verified"
    except HTTPError as exc:
        return False, f"HTTP {exc.code} during source feasibility probe"
    except URLError as exc:
        return False, f"network failure during source feasibility probe: {exc.reason}"
    except TimeoutError:
        return False, "timeout during source feasibility probe"


def build_jobs(
    fetcher: GitHubFetcher,
    *,
    collected_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Return no jobs unless a source proves an employer posting timestamp.

    The accessible SimplifyJobs dataset is inspected for its documented
    timestamp semantics and rejected because its date_posted represents when a
    listing was added to that list, not when an employer posted the role.
    Greenhouse and Lever probes are recorded only as feasibility checks; their
    response or probe time is never substituted for posted_at.
    """

    checks: list[dict[str, Any]] = []
    simplify_url = (
        f"{GITHUB_API_BASE}/repos/SimplifyJobs/Summer2027-Internships/contents/CONTRIBUTING.md"
    )
    try:
        payload = fetcher.get_json(simplify_url)
        content = payload.get("content") if isinstance(payload, dict) else None
        try:
            decoded = base64.b64decode(content).decode("utf-8", "replace") if isinstance(content, str) else ""
        except (ValueError, UnicodeDecodeError) as exc:
            raise SourceFetchFailure("SimplifyJobs documentation content could not be decoded") from exc
        documented = "when added" in decoded.casefold()
        checks.append(
            {
                "source_name": "SimplifyJobs Summer2027 Internships listings",
                "url": simplify_url,
                "checked_at": _iso(collected_at),
                "status": "rejected",
                "reason": (
                    "Source documentation defines date_posted as a Unix timestamp when added to the listing, "
                    "not an employer posting timestamp; no jobs were accepted."
                    if documented
                    else "Timestamp semantics could not be verified from the accessible source documentation; no jobs were accepted."
                ),
                "required_missing_or_invalid_field": "actual employer posted_at",
            }
        )
    except SourceFetchFailure as exc:
        checks.append(
            {
                "source_name": "SimplifyJobs Summer2027 Internships listings",
                "url": simplify_url,
                "checked_at": _iso(collected_at),
                "status": "unusable",
                "reason": str(exc),
                "required_missing_or_invalid_field": "actual employer posted_at",
            }
        )

    for source_name, url in (
        ("Greenhouse OpenAI board", "https://boards-api.greenhouse.io/v1/boards/openai/jobs?content=true"),
        ("Lever Anthropic board", "https://api.lever.co/v0/postings/anthropic?mode=json"),
    ):
        reachable, reason = _probe_url(url)
        checks.append(
            {
                "source_name": source_name,
                "url": url,
                "checked_at": _iso(collected_at),
                "status": "reachable_unvalidated" if reachable else "unusable",
                "reason": reason,
                "required_missing_or_invalid_field": "actual employer posted_at",
            }
        )

    metrics = {
        "accepted_rows": 0,
        "freshness_requirement": "An accepted Job requires an actual employer posted_at timestamp within the prior 24 hours; crawl, response, and page-update times are not substitutes.",
        "rejected_by_reason": {
            "source_timestamp_semantics_invalid_or_unavailable": len(checks),
        },
        "source_checks": len(checks),
    }
    return [], metrics, checks


def _valid_provenance(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def validate_graphone_records(
    *,
    startups: list[dict[str, Any]],
    products: list[dict[str, Any]],
    research_papers: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    news: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    generated_at: datetime,
    freshness_window_start: datetime,
) -> dict[str, Any]:
    """Apply explicit, non-inferential GraphOne output gates."""

    failures: list[dict[str, Any]] = []
    all_records: list[tuple[str, dict[str, Any]]] = []
    all_records.extend(("startup", record) for record in startups)
    all_records.extend(("product", record) for record in products)
    all_records.extend(("research_paper", record) for record in research_papers)
    all_records.extend(("job", record) for record in jobs)
    all_records.extend(("news", record) for record in news)

    seen_ids: set[str] = set()
    for record_type, record in all_records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            failures.append({"type": "missing_id", "record_type": record_type, "record_id": record_id})
        elif record_id in seen_ids:
            failures.append({"type": "duplicate_id", "record_type": record_type, "record_id": record_id})
        else:
            seen_ids.add(record_id)
        if not _is_http_url(record.get("source_url")):
            failures.append({"type": "invalid_source_url", "record_type": record_type, "record_id": record_id})
        if not _parse_timestamp(record.get("collectedAt")):
            failures.append({"type": "invalid_collected_at", "record_type": record_type, "record_id": record_id})
        if not _valid_provenance(record.get("provenance")):
            failures.append({"type": "missing_provenance", "record_type": record_type, "record_id": record_id})

        if record_type == "startup":
            if not _clean_text(record.get("canonical_name")):
                failures.append({"type": "missing_startup_name", "record_id": record_id})
            if not isinstance(record.get("employee_count"), int) or record["employee_count"] <= 0:
                failures.append({"type": "invalid_employee_count", "record_id": record_id})
        elif record_type == "product":
            if not _clean_text(record.get("product_name")) or not _is_http_url(record.get("product_url")):
                failures.append({"type": "invalid_product_identity", "record_id": record_id})
            if not _clean_text(record.get("description")):
                failures.append({"type": "missing_product_description", "record_id": record_id})
            if not isinstance(record.get("provenance", {}).get("ai_relevance_evidence"), dict):
                failures.append({"type": "missing_product_ai_evidence", "record_id": record_id})
        elif record_type == "research_paper":
            if record.get("recordType") != "RESEARCH_PAPER" or not _is_http_url(record.get("paper_url")):
                failures.append({"type": "invalid_research_identity", "record_id": record_id})
            if not _parse_timestamp(record.get("published_date")):
                failures.append({"type": "invalid_research_published_date", "record_id": record_id})
        elif record_type == "job":
            required = ("company", "title", "url", "location", "posted_at", "remote_status", "role_family", "source")
            if any(not _clean_text(record.get(field)) for field in required):
                failures.append({"type": "missing_job_required_field", "record_id": record_id})
            posted_at = _parse_timestamp(record.get("posted_at"))
            if posted_at is None or posted_at < freshness_window_start or posted_at > generated_at:
                failures.append({"type": "job_outside_freshness_window", "record_id": record_id})
        elif record_type == "news":
            required = ("title", "canonical_url", "publisher", "published_at", "timestamp_semantics")
            if any(not _clean_text(record.get(field)) for field in required):
                failures.append({"type": "missing_news_required_field", "record_id": record_id})
            published_at = _parse_timestamp(record.get("published_at"))
            if published_at is None or published_at < freshness_window_start or published_at > generated_at:
                failures.append({"type": "news_outside_freshness_window", "record_id": record_id})
            if record.get("timestamp_semantics") != "github_release_published_at":
                failures.append({"type": "invalid_news_timestamp_semantics", "record_id": record_id})
            if not isinstance(record.get("provenance", {}).get("ai_relevance_evidence"), dict):
                failures.append({"type": "missing_news_ai_evidence", "record_id": record_id})

    mapping_ids = [mapping.get("canonical_id") for mapping in mappings]
    mapping_count = Counter(mapping_ids)
    for record_id in seen_ids:
        if mapping_count[record_id] != 1:
            failures.append(
                {
                    "type": "mapping_coverage_failure",
                    "record_id": record_id,
                    "mapping_entries": mapping_count[record_id],
                }
            )
    for mapping in mappings:
        if not _is_http_url(mapping.get("source_url")):
            failures.append({"type": "mapping_invalid_source_url", "record_id": mapping.get("canonical_id")})

    summary = {
        "startups": len(startups),
        "products": len(products),
        "research_papers": len(research_papers),
        "jobs": len(jobs),
        "news": len(news),
        "entity_mapping_log": len(mappings),
        "total_records": len(all_records),
        "mapping_coverage": (sum(mapping_count[record_id] == 1 for record_id in seen_ids) / len(seen_ids)) if seen_ids else 1.0,
        "provenance_coverage": (
            sum(_valid_provenance(record.get("provenance")) for _, record in all_records) / len(all_records)
            if all_records
            else 1.0
        ),
        "freshness_window_start": _iso(freshness_window_start),
        "freshness_window_end": _iso(generated_at),
    }
    return {
        "status": "passed" if not failures else "failed",
        "summary": summary,
        "failures": failures,
        "failure_counts_by_type": dict(sorted(Counter(failure["type"] for failure in failures).items())),
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_csv(path: Path, columns: list[str], records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record.get(column)) for column in columns})
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _package_payload(
    record_type: str,
    generated_at: datetime,
    records: list[dict[str, Any]],
    *,
    notes: list[str] | None = None,
    source_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "1.0",
        "recordType": record_type,
        "generatedAt": _iso(generated_at),
        "records": records,
    }
    if notes:
        payload["notes"] = notes
    if source_checks is not None:
        payload["source_checks"] = source_checks
    return payload


def build_graphone_outputs(
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    *,
    now: datetime | None = None,
    fetcher: GitHubFetcher | None = None,
    startup_limit: int = STARTUP_LIMIT,
    product_limit: int = PRODUCT_LIMIT,
    news_repositories: Iterable[str] = NEWS_REPOSITORIES,
) -> dict[str, Any]:
    """Build every GraphOne artifact and return its validated report.

    Required remote source data is fetched into memory first.  The function
    raises before writing when a mandatory snapshot is unavailable, when the
    research output is invalid, or when validation fails.
    """

    generated_at = _utc_now(now)
    fetcher = fetcher or GitHubFetcher(token=os.environ.get("GITHUB_TOKEN"))
    news_repositories = tuple(news_repositories)

    startups, startup_mappings, startup_metrics = build_startups(
        fetcher, collected_at=generated_at, limit=startup_limit
    )
    products, product_mappings, product_metrics = build_products(
        fetcher, collected_at=generated_at, limit=product_limit
    )
    research, research_mappings, research_metrics = build_research_papers(collected_at=generated_at)
    news, news_mappings, news_metrics, news_source_checks = build_news(
        fetcher, collected_at=generated_at, repositories=news_repositories
    )
    jobs, jobs_metrics, job_source_checks = build_jobs(fetcher, collected_at=generated_at)
    mappings = [*startup_mappings, *product_mappings, *research_mappings, *news_mappings]

    validation = validate_graphone_records(
        startups=startups,
        products=products,
        research_papers=research,
        jobs=jobs,
        news=news,
        mappings=mappings,
        generated_at=generated_at,
        freshness_window_start=generated_at - NEWS_LOOKBACK,
    )
    if validation["status"] != "passed":
        raise GraphOneValidationError(json.dumps(validation["failure_counts_by_type"], sort_keys=True))

    output_dir = Path(output_dir)
    source_coverage = {
        "startups": [startup_metrics["source_name"]],
        "products": [product_metrics["source_name"]],
        "research_papers": [research_metrics["source_name"]],
        "news": ["GitHub REST Releases API"],
        "jobs": [],
    }
    rejected_report = {
        "generatedAt": _iso(generated_at),
        "startups": {
            "rejected_by_reason": startup_metrics["rejected_by_reason"],
            "valid_rows_not_exported_due_target_limit": startup_metrics["valid_rows_not_exported_due_target_limit"],
        },
        "products": {
            "rejected_by_reason": product_metrics["rejected_by_reason"],
            "valid_rows_not_exported_due_target_limit": product_metrics["valid_rows_not_exported_due_target_limit"],
        },
        "research_papers": {"rejected_by_reason": research_metrics["rejected_by_reason"]},
        "news": {"rejected_by_reason": news_metrics["rejected_by_reason"]},
        "jobs": {
            "rejected_by_reason": jobs_metrics["rejected_by_reason"],
            "source_checks": job_source_checks,
        },
    }
    validation.update(
        {
            "generatedAt": _iso(generated_at),
            "source_coverage": source_coverage,
            "per_tab": {
                "Startups": startup_metrics,
                "Products": product_metrics,
                "Research Papers": research_metrics,
                "Jobs": jobs_metrics,
                "News": news_metrics,
                "Entity Mapping Log": {
                    "accepted_rows": len(mappings),
                    "mapping_coverage": validation["summary"]["mapping_coverage"],
                    "methods": dict(sorted(Counter(mapping["method"] for mapping in mappings).items())),
                },
            },
            "rejected_records": rejected_report,
            "source_checks": {"news": news_source_checks, "jobs": job_source_checks},
        }
    )
    manifest = {
        "schemaVersion": "1.0",
        "generatedAt": _iso(generated_at),
        "purpose": (
            "Separate GraphOne trial source-of-truth artifacts. AI Orbit entity/relationship JSON is not used to meet "
            "the GraphOne 1,000 startup/product/research-paper targets."
        ),
        "sources": {
            "startups": {
                **YC_VAULT_SOURCE,
                "source_file_url": _blob_url(YC_VAULT_SOURCE),
                "source_blob_api_url": _blob_api_url(YC_VAULT_SOURCE),
                "selection": "Active YC-directory snapshot rows with direct positive Team Size; first 1,000 in source order after gates.",
            },
            "products": {
                **AI_TOOLS_LIST_SOURCE,
                "source_file_url": _blob_url(AI_TOOLS_LIST_SOURCE),
                "source_blob_api_url": _blob_api_url(AI_TOOLS_LIST_SOURCE),
                "selection": "First 1,000 distinct product URLs after direct identity, AI-evidence, and non-editorial semantics gates.",
            },
            "research_papers": {
                "input": str(RESEARCH_PAPERS_INPUT.relative_to(PROJECT_ROOT)),
                "preservation": "Existing 1,000-row output copied without a new network ingestion run.",
            },
            "news": {
                "repositories": list(news_repositories),
                "selection": "Non-draft, non-prerelease GitHub releases with source release published_at inside the final 24-hour window and observed repository AI relevance.",
            },
            "jobs": {
                "selection": "No rows accepted without a source-proven employer posted_at timestamp.",
            },
        },
        "tabs": ["Startups", "Products", "Research Papers", "Jobs", "News", "Entity Mapping Log"],
    }

    # Only after all remote retrieval and validation succeeds do we replace
    # individual final artifacts.  A temporary source/network outage has
    # already raised above and leaves an earlier verified corpus untouched.
    _write_json(
        output_dir / "startups.json",
        _package_payload(
            "STARTUP",
            generated_at,
            startups,
            notes=[
                "Source is a dated public YC-directory snapshot; employee counts are source observations, not current re-verifications.",
                "No position-based join to the separate YC_URLs.csv was used because that file has no company-name join key.",
            ],
        ),
    )
    _write_json(
        output_dir / "products.json",
        _package_payload(
            "PRODUCT",
            generated_at,
            products,
            notes=[
                "Provider/company and pricing model remain null because the selected source does not supply them.",
                "Packages, repositories, models, features, tasks, and editorial descriptions are not treated as Product records without direct product identity evidence.",
            ],
        ),
    )
    _write_json(
        output_dir / "research_papers.json",
        _package_payload(
            "RESEARCH_PAPER",
            generated_at,
            research,
            notes=["Preserved from the existing validated 1,000-paper export; this build did not re-ingest arXiv."],
        ),
    )
    _write_json(
        output_dir / "jobs.json",
        _package_payload(
            "JOB",
            generated_at,
            jobs,
            notes=[
                "No accepted jobs: no investigated source established an actual employer posting timestamp within the required 24-hour window.",
                "Crawl, response, page-update, and listing-added timestamps were not substituted for posted_at.",
            ],
            source_checks=job_source_checks,
        ),
    )
    _write_json(
        output_dir / "news.json",
        _package_payload(
            "NEWS",
            generated_at,
            news,
            notes=[
                "Each accepted record is a GitHub release announcement, not a general press article.",
                "published_at uses GitHub's release publication semantics and is constrained to the final 24-hour window.",
            ],
            source_checks=news_source_checks,
        ),
    )
    _write_json(output_dir / "entity_mapping_log.json", mappings)
    _write_json(output_dir / "rejected_records.json", rejected_report)
    _write_json(output_dir / "validation_report.json", validation)
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_csv(output_dir / "sheets" / "Startups.csv", STARTUP_COLUMNS, startups)
    _write_csv(output_dir / "sheets" / "Products.csv", PRODUCT_COLUMNS, products)
    _write_csv(output_dir / "sheets" / "Research Papers.csv", RESEARCH_COLUMNS, research)
    _write_csv(output_dir / "sheets" / "Jobs.csv", JOB_COLUMNS, jobs)
    _write_csv(output_dir / "sheets" / "News.csv", NEWS_COLUMNS, news)
    _write_csv(output_dir / "sheets" / "Entity Mapping Log.csv", MAPPING_COLUMNS, mappings)
    return validation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build validated, separate GraphOne trial artifacts.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--startup-limit", type=int, default=STARTUP_LIMIT)
    parser.add_argument("--product-limit", type=int, default=PRODUCT_LIMIT)
    args = parser.parse_args(argv)
    report = build_graphone_outputs(
        args.output_dir,
        startup_limit=args.startup_limit,
        product_limit=args.product_limit,
    )
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
