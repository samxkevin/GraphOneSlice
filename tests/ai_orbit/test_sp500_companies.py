"""Regression tests for S&P 500 company-metadata enrichment.

The adapter may populate founding_year / industry_sector / headquarters only
from an S&P constituent row matched to a GitHub organization. GitHub org
created_at is never founding year. Unmatched orgs and hollow org payloads
produce no records.
"""

from datetime import datetime, timezone

import pytest

from src.ai_orbit.adapters.sp500_companies import (
    SP500CompanyMetadataAdapter,
    github_org_keys,
    match_sp500_row,
    parse_founded_year,
    sp500_row_keys,
)
from src.ai_orbit.config import AIOrbitSettings
from src.ai_orbit.utils.identity import normalize_name


def _adapter() -> SP500CompanyMetadataAdapter:
    return SP500CompanyMetadataAdapter(AIOrbitSettings(log_level="CRITICAL"))


def test_parse_founded_year_accepts_plain_year():
    assert parse_founded_year("1985") == 1985
    assert parse_founded_year("1993") == 1993


def test_parse_founded_year_uses_current_legal_entity_year():
    # datapackage: "2013 (1888)" = current legal entity, predecessor in parens
    assert parse_founded_year("2013 (1888)") == 2013


def test_parse_founded_year_rejects_empty_and_non_years():
    assert parse_founded_year(None) is None
    assert parse_founded_year("") is None
    assert parse_founded_year("unknown") is None
    assert parse_founded_year("1799") is None


def test_github_created_at_is_not_a_founded_year():
    # GitHub org created_at is an ISO timestamp, not S&P Founded.
    assert parse_founded_year("2019-09-13T18:49:06Z") is None
    assert parse_founded_year("2014-05-02T04:39:32Z") is None


def test_sp500_row_keys_include_ticker_and_share_class_stripped_name():
    row = {
        "Symbol": "GOOGL",
        "Security": "Alphabet Inc. (Class A)",
        "GICS Sector": "Communication Services",
        "Headquarters Location": "Mountain View, California",
        "Founded": "1998",
    }
    keys = sp500_row_keys(row)
    assert "googl" in keys
    assert normalize_name("Alphabet Inc. (Class A)") in keys
    assert normalize_name("Alphabet Inc.") in keys


def test_qualcomm_org_matches_qualcomm_constituent_not_qcom_alone():
    org = {"login": "qualcomm", "name": "Qualcomm Technologies, Inc.", "html_url": "https://github.com/qualcomm", "description": "desc"}
    rows = [
        {
            "Symbol": "QCOM",
            "Security": "Qualcomm",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "San Diego, California",
            "Founded": "1985",
        },
        {
            "Symbol": "IBM",
            "Security": "IBM",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "Armonk, New York",
            "Founded": "1911",
        },
    ]
    matched = match_sp500_row(org, rows)
    assert matched is not None
    assert matched["Symbol"] == "QCOM"


def test_ibm_login_matches_ibm_ticker_and_security():
    org = {"login": "ibm", "name": "International Business Machines", "html_url": "https://github.com/IBM", "description": "Open Source @ IBM"}
    rows = [
        {
            "Symbol": "IBM",
            "Security": "IBM",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "Armonk, New York",
            "Founded": "1911",
        }
    ]
    assert "ibm" in github_org_keys(org)
    matched = match_sp500_row(org, rows)
    assert matched is not None
    assert matched["Security"] == "IBM"


def test_google_org_does_not_match_alphabet_without_alias():
    org = {"login": "google", "name": "Google", "html_url": "https://github.com/google", "description": "Google Open Source"}
    rows = [
        {
            "Symbol": "GOOGL",
            "Security": "Alphabet Inc. (Class A)",
            "GICS Sector": "Communication Services",
            "Headquarters Location": "Mountain View, California",
            "Founded": "1998",
        }
    ]
    assert match_sp500_row(org, rows) is None


def test_ambiguous_multi_row_match_is_rejected():
    org = {"login": "acme", "name": "Acme", "html_url": "https://github.com/acme", "description": "x"}
    rows = [
        {"Symbol": "AAA", "Security": "Acme", "GICS Sector": "IT", "Headquarters Location": "X", "Founded": "2000"},
        {"Symbol": "BBB", "Security": "Acme", "GICS Sector": "IT", "Headquarters Location": "Y", "Founded": "2001"},
    ]
    assert match_sp500_row(org, rows) is None


def test_record_requires_description_and_sp500_fields():
    adapter = _adapter()
    now = datetime.now(timezone.utc)
    rows = [
        {
            "Symbol": "QCOM",
            "Security": "Qualcomm",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "San Diego, California",
            "Founded": "1985",
        }
    ]
    hollow = {
        "login": "qualcomm",
        "name": "Qualcomm Technologies, Inc.",
        "html_url": "https://github.com/qualcomm",
        "description": "",
        "created_at": "2019-09-13T18:49:06Z",
    }
    assert adapter._record_from_org(hollow, rows, source_url="https://api.github.com/repos/datasets/s-and-p-500-companies/contents/data/constituents.csv", evidence_url="https://github.com/datasets/s-and-p-500-companies/blob/main/data/constituents.csv", fetched_at=now) is None

    org = {
        "login": "qualcomm",
        "name": "Qualcomm Technologies, Inc.",
        "html_url": "https://github.com/qualcomm",
        "description": "At Qualcomm Technologies, Inc., we transform how the world connects, computes and communicates.",
        "created_at": "2019-09-13T18:49:06Z",
    }
    record = adapter._record_from_org(
        org,
        rows,
        source_url="https://api.github.com/repos/datasets/s-and-p-500-companies/contents/data/constituents.csv",
        evidence_url="https://github.com/datasets/s-and-p-500-companies/blob/main/data/constituents.csv",
        fetched_at=now,
    )
    assert record is not None
    assert record.entity_type == "company"
    assert record.name == "Qualcomm"
    assert record.url == "https://github.com/qualcomm"
    company = record.metadata["company"]
    assert company["founding_year"] == 1985
    assert company["industry_sector"] == "Information Technology"
    assert company["headquarters"] == "San Diego, California"
    assert company["github_created_at_not_used_as_founding_year"] is True
    assert company["github_created_at_observed"] == "2019-09-13T18:49:06Z"
    assert company["founding_year"] != 2019
    assert company["founding_year_evidence"]["field"] == "Founded"
    assert company["founding_year_evidence"]["semantics"] == "sp500_founded_year"


def test_record_skips_org_without_sp500_match():
    adapter = _adapter()
    now = datetime.now(timezone.utc)
    org = {
        "login": "huggingface",
        "name": "Hugging Face",
        "html_url": "https://github.com/huggingface",
        "description": "The AI community building the future.",
    }
    rows = [
        {
            "Symbol": "QCOM",
            "Security": "Qualcomm",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "San Diego, California",
            "Founded": "1985",
        }
    ]
    assert adapter._record_from_org(
        org,
        rows,
        source_url="https://example.com/csv",
        evidence_url="https://example.com/csv",
        fetched_at=now,
    ) is None


def test_record_skips_row_missing_headquarters():
    adapter = _adapter()
    now = datetime.now(timezone.utc)
    org = {
        "login": "ibm",
        "name": "IBM",
        "html_url": "https://github.com/IBM",
        "description": "Open Source @ IBM",
    }
    rows = [
        {
            "Symbol": "IBM",
            "Security": "IBM",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "",
            "Founded": "1911",
        }
    ]
    assert adapter._record_from_org(
        org,
        rows,
        source_url="https://example.com/csv",
        evidence_url="https://example.com/csv",
        fetched_at=now,
    ) is None


@pytest.mark.asyncio
async def test_discover_skips_unmatched_configured_orgs(monkeypatch):
    settings = AIOrbitSettings(log_level="CRITICAL", sp500_github_orgs=["qualcomm", "huggingface"])
    adapter = SP500CompanyMetadataAdapter(settings)
    adapter._rows = [
        {
            "Symbol": "QCOM",
            "Security": "Qualcomm",
            "GICS Sector": "Information Technology",
            "Headquarters Location": "San Diego, California",
            "Founded": "1985",
        }
    ]
    adapter._csv_response_url = "https://api.github.com/repos/datasets/s-and-p-500-companies/contents/data/constituents.csv"
    adapter._csv_html_url = "https://github.com/datasets/s-and-p-500-companies/blob/main/data/constituents.csv"

    async def fake_org(login: str):
        if login == "qualcomm":
            return {
                "login": "qualcomm",
                "name": "Qualcomm Technologies, Inc.",
                "html_url": "https://github.com/qualcomm",
                "description": "At Qualcomm Technologies, Inc., we transform how the world connects.",
                "created_at": "2019-09-13T18:49:06Z",
            }
        return {
            "login": "huggingface",
            "name": "Hugging Face",
            "html_url": "https://github.com/huggingface",
            "description": "The AI community building the future.",
        }

    monkeypatch.setattr(adapter, "_fetch_org", fake_org)
    records = await adapter.discover()
    assert len(records) == 1
    assert records[0].name == "Qualcomm"
    assert records[0].metadata["company"]["founding_year"] == 1985
