"""S&P 500 constituent metadata for already-evidenced AI company identities.

The AI Orbit company schema requires founding_year, industry_sector, and
headquarters. GitHub organization records do not supply those fields, and
Wikidata/ROR/Wikipedia are unreachable from this environment (TLS EOF).

`datasets/s-and-p-500-companies` is a GitHub-hosted, parseable CSV whose
datapackage documents:

* Founded — year the company was founded
* GICS Sector — industry sector
* Headquarters Location — city/state (or country) of headquarters

This adapter does **not** ingest the 500-index as filler companies. It only
emits a company record when all of the following are observed:

1. a configured GitHub organization login (bounded to model-provider orgs
   already present in this dataset) returns name + html_url + description;
2. that org matches exactly one S&P constituent via deterministic keys
   (normalized security name, share-class-stripped name, ticker symbol,
   GitHub login);
3. the matched row supplies Founded, GICS Sector, and Headquarters Location.

GitHub ``created_at`` is never treated as founding year. Missing S&P fields
stay null rather than being inferred.
"""

from __future__ import annotations

import base64
import csv
import io
import re
from datetime import datetime, timezone
from typing import Any

from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.models import RawEntityRecord, SourceFeasibility
from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError
from src.ai_orbit.utils.identity import normalize_name
from src.ai_orbit.utils.url import normalize_url


_REQUIRED_COLUMNS = (
    "Symbol",
    "Security",
    "GICS Sector",
    "Headquarters Location",
    "Founded",
)

_SHARE_CLASS_SUFFIX = re.compile(r"\s*\(class\s+[a-z]\)\s*$", re.IGNORECASE)
# Accept a four-digit year, optionally followed by a predecessor year in
# parentheses (datapackage example: "2013 (1888)"). Reject ISO timestamps
# such as GitHub org created_at ("2019-09-13T18:49:06Z").
_FOUNDED_YEAR = re.compile(r"^\s*(\d{4})(?:\s*\([^)]+\))?\s*$")


def parse_founded_year(raw: str | None) -> int | None:
    """Parse S&P ``Founded`` as the current legal-entity year.

    The datapackage describes values such as ``2013 (1888)`` as the current
    legal entity year followed by a predecessor year in parentheses. Only the
    leading four-digit year is accepted. GitHub org created_at is not a valid
    input to this function.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    match = _FOUNDED_YEAR.match(raw)
    if not match:
        return None
    year = int(match.group(1))
    if year < 1800 or year > datetime.now(timezone.utc).year:
        return None
    return year


def sp500_row_keys(row: dict[str, str]) -> set[str]:
    """Deterministic lookup keys for one constituent row."""
    security = (row.get("Security") or "").strip()
    symbol = (row.get("Symbol") or "").strip().lower()
    keys: set[str] = set()
    if security:
        keys.add(normalize_name(security))
        stripped = _SHARE_CLASS_SUFFIX.sub("", security).strip()
        if stripped:
            keys.add(normalize_name(stripped))
    if symbol:
        keys.add(symbol)
    keys.discard("")
    return keys


def github_org_keys(org: dict[str, Any]) -> set[str]:
    """Deterministic lookup keys for a GitHub organization payload."""
    keys: set[str] = set()
    name = (org.get("name") or "").strip()
    login = (org.get("login") or "").strip().lower()
    if name:
        keys.add(normalize_name(name))
    if login:
        keys.add(login)
        keys.add(normalize_name(login))
    keys.discard("")
    return keys


def match_sp500_row(org: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, str] | None:
    """Return the unique S&P row whose keys intersect the org keys, else None."""
    org_keys = github_org_keys(org)
    if not org_keys:
        return None
    matches: list[dict[str, str]] = []
    seen_symbols: set[str] = set()
    for row in rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        if symbol in seen_symbols:
            continue
        if org_keys & sp500_row_keys(row):
            matches.append(row)
            seen_symbols.add(symbol)
    if len(matches) != 1:
        return None
    return matches[0]


class SP500CompanyMetadataAdapter(SourceAdapter):
    name = "S&P 500 Companies Dataset"

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
        self._rows: list[dict[str, str]] | None = None
        self._csv_response_url: str | None = None
        self._csv_html_url: str | None = None

    async def verify(self) -> SourceFeasibility:
        url = self.settings.sp500_constituents_api_url
        try:
            rows, response_url, html_url = await self._fetch_rows()
            self._rows = rows
            self._csv_response_url = response_url
            self._csv_html_url = html_url
            columns = list(rows[0].keys()) if rows else []
            missing = [column for column in _REQUIRED_COLUMNS if column not in columns]
            if missing:
                return SourceFeasibility(
                    source_name=self.name,
                    source_type="GitHub-hosted CSV + datapackage",
                    access_method="GitHub REST contents API for datasets/s-and-p-500-companies data/constituents.csv",
                    url=response_url,
                    status="unusable",
                    domain="Companies",
                    http_status=200,
                    required_fields=list(_REQUIRED_COLUMNS),
                    available_fields=columns,
                    authentication_required=False,
                    anti_bot_js="GitHub REST API returned CSV as JSON/base64; no browser automation or JavaScript required",
                    inventory_evidence=f"constituent rows={len(rows)}; missing required columns={missing}",
                    company_identity_quality="CSV identifies listed company names and tickers; it is not used as a company URL source",
                    actual_crawl_feasibility="reachable but missing required Founded/GICS Sector/Headquarters Location columns",
                    failure_behavior=f"constituents.csv missing required columns: {missing}",
                )
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted CSV + datapackage",
                access_method="GitHub REST contents API for datasets/s-and-p-500-companies data/constituents.csv",
                url=response_url,
                status="usable",
                domain="Companies",
                http_status=200,
                pagination="single constituents.csv document; adapter does not ingest the full index",
                available_fields=columns,
                required_fields=list(_REQUIRED_COLUMNS),
                authentication_required=False,
                freshness="Founded is the source-documented founding year, not GitHub org created_at or index Date added",
                anti_bot_js="GitHub REST API returned CSV as JSON/base64; no browser automation or JavaScript required",
                inventory_evidence=(
                    f"constituent rows={len(rows)}; configured GitHub org lookups="
                    f"{len(self.settings.sp500_github_orgs)}; records are emitted only on a unique "
                    "org↔constituent match with Founded + GICS Sector + Headquarters Location"
                ),
                company_identity_quality=(
                    "identity is the official GitHub organization (login/html_url/description); "
                    "founding year, GICS sector, and headquarters are taken only from the matched S&P row"
                ),
                ai_relevance=(
                    "configured org logins are AI model providers already observed in this dataset "
                    "(Qualcomm/IBM/NVIDIA/Google); the full S&P 500 is not ingested"
                ),
                actual_crawl_feasibility="usable for bounded company-metadata enrichment of matched GitHub orgs",
                record_volume_estimate=f"S&P constituents={len(rows)}; org lookup bound={len(self.settings.sp500_github_orgs)}",
                failure_behavior="403/404/malformed CSV are source failures; unmatched orgs are skipped without failing the source; 429/5xx use bounded retry",
            )
        except SourceFetchError as exc:
            return SourceFeasibility(
                source_name=self.name,
                source_type="GitHub-hosted CSV + datapackage",
                access_method="GitHub REST contents API for datasets/s-and-p-500-companies data/constituents.csv",
                url=url,
                status="unusable",
                domain="Companies",
                http_status=exc.status_code,
                required_fields=list(_REQUIRED_COLUMNS),
                authentication_required=False,
                anti_bot_js="not determined; API request failed",
                actual_crawl_feasibility="not usable from this environment based on observed failure",
                failure_behavior=f"{exc.failure_class.value}: {exc}",
            )

    async def discover(self) -> list[RawEntityRecord]:
        if self._rows is None:
            await self.verify()
        rows = self._rows or []
        source_url = self._csv_response_url or self.settings.sp500_constituents_api_url
        evidence_url = self._csv_html_url or source_url
        now = datetime.now(timezone.utc)
        records: list[RawEntityRecord] = []
        for login in self.settings.sp500_github_orgs:
            org = await self._fetch_org(login)
            if org is None:
                continue
            record = self._record_from_org(org, rows, source_url=source_url, evidence_url=evidence_url, fetched_at=now)
            if record is not None:
                records.append(record)
        return records

    async def _fetch_rows(self) -> tuple[list[dict[str, str]], str, str | None]:
        response = await self.client.get_json(self.settings.sp500_constituents_api_url)
        data = response.data
        if not isinstance(data, dict):
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "unexpected GitHub contents payload for S&P 500 constituents.csv")
        content = data.get("content")
        encoding = data.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "missing base64 content for S&P 500 constituents.csv")
        try:
            text = base64.b64decode(content).decode("utf-8", "replace")
        except ValueError as exc:
            raise SourceFetchError(FailureClass.MALFORMED_JSON, "malformed base64 for S&P 500 constituents.csv") from exc
        parsed = list(csv.DictReader(io.StringIO(text)))
        html_url = data.get("html_url") if isinstance(data.get("html_url"), str) else None
        return parsed, response.url, html_url

    async def _fetch_org(self, login: str) -> dict[str, Any] | None:
        url = f"{self.settings.github_api_base.rstrip('/')}/orgs/{login}"
        try:
            response = await self.client.get_json(url)
        except SourceFetchError:
            return None
        data = response.data
        return data if isinstance(data, dict) else None

    def _record_from_org(
        self,
        org: dict[str, Any],
        rows: list[dict[str, str]],
        *,
        source_url: str,
        evidence_url: str,
        fetched_at: datetime,
    ) -> RawEntityRecord | None:
        login = (org.get("login") or "").strip()
        description = (org.get("description") or "").strip()
        html_url = org.get("html_url")
        if not login or not description or not html_url:
            return None
        row = match_sp500_row(org, rows)
        if row is None:
            return None
        founded_raw = (row.get("Founded") or "").strip()
        founding_year = parse_founded_year(founded_raw)
        industry = (row.get("GICS Sector") or "").strip() or None
        headquarters = (row.get("Headquarters Location") or "").strip() or None
        if founding_year is None or not industry or not headquarters:
            return None
        security = (row.get("Security") or "").strip()
        symbol = (row.get("Symbol") or "").strip()
        if not security or not symbol:
            return None
        # S&P Security is the listed company name (e.g. IBM, Qualcomm, Nvidia).
        # GitHub org created_at is intentionally not copied into founding_year.
        return RawEntityRecord(
            source_key=f"sp500:company:{symbol.lower()}",
            entity_type="company",
            name=security,
            description=description,
            url=normalize_url(html_url),
            categories=["Companies"],
            source_name=self.name,
            source_url=source_url,
            raw={
                "github_org": {
                    "login": login,
                    "name": org.get("name"),
                    "html_url": html_url,
                    "description": description,
                    "created_at": org.get("created_at"),
                },
                "sp500": {
                    "Symbol": symbol,
                    "Security": security,
                    "GICS Sector": industry,
                    "GICS Sub-Industry": row.get("GICS Sub-Industry"),
                    "Headquarters Location": headquarters,
                    "Founded": founded_raw,
                    "CIK": row.get("CIK"),
                },
            },
            metadata={
                "company": {
                    "founding_year": founding_year,
                    "industry_sector": industry,
                    "headquarters": headquarters,
                    "founding_year_evidence": {
                        "field": "Founded",
                        "value": founded_raw,
                        "source_url": evidence_url,
                        "semantics": "sp500_founded_year",
                    },
                    "industry_sector_evidence": {
                        "field": "GICS Sector",
                        "value": industry,
                        "source_url": evidence_url,
                    },
                    "headquarters_evidence": {
                        "field": "Headquarters Location",
                        "value": headquarters,
                        "source_url": evidence_url,
                    },
                    "sp500_symbol": symbol,
                    "sp500_security": security,
                    "github_login": login,
                    "github_created_at_observed": org.get("created_at"),
                    "github_created_at_not_used_as_founding_year": True,
                }
            },
            fetched_at=fetched_at,
        )
