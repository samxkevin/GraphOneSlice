from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class FetchStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class PaperStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    FETCHED = "FETCHED"
    PARSED = "PARSED"
    RESOLVING_REPO = "RESOLVING_REPO"
    RESOLVED = "RESOLVED"
    VALIDATED = "VALIDATED"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"


class EvidenceType(str, Enum):
    AUTHORITATIVE_PAPER_PAGE = "authoritative_paper_page"
    TRUSTED_METADATA = "trusted_metadata"
    PWC_VERIFIED = "pwc_verified"
    PWC_AI_AGENT_PARSED = "pwc_ai_agent_parsed"


# strongest -> weakest, matches the agreed evidence-tier policy
EVIDENCE_STRENGTH: dict[EvidenceType, int] = {
    EvidenceType.AUTHORITATIVE_PAPER_PAGE: 1,
    EvidenceType.TRUSTED_METADATA: 2,
    EvidenceType.PWC_VERIFIED: 3,
    EvidenceType.PWC_AI_AGENT_PARSED: 4,
}


class AssociationMethod(str, Enum):
    EXPLICIT_LINK_PARSED = "explicit_link_parsed"
    METADATA_FIELD = "metadata_field"
    PWC_API_FIELD = "pwc_api_field"


class GithubApiStatus(str, Enum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"


# ---------------------------------------------------------------
# Raw evidence
# ---------------------------------------------------------------
class FetchObservation(BaseModel):
    source_name: str
    source_url: str
    raw_payload: dict[str, Any]
    content_hash: str
    fetched_at: datetime
    http_status: int | None = None
    fetch_status: FetchStatus


# ---------------------------------------------------------------
# Deterministically parsed paper (no LLM involved)
# ---------------------------------------------------------------
class ParsedPaper(BaseModel):
    arxiv_id: str
    canonical_url: str
    title: str
    authors: list[str]
    abstract: str | None = None
    published_date: datetime | None = None

    @field_validator("arxiv_id")
    @classmethod
    def non_empty_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("arxiv_id must not be empty")
        return v.strip()

    @field_validator("authors")
    @classmethod
    def non_empty_authors(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("authors must not be empty")
        return v


# ---------------------------------------------------------------
# Repository association candidate (evidence-backed, never invented)
# ---------------------------------------------------------------
class RepoLinkCandidate(BaseModel):
    repo_url: str
    evidence_type: EvidenceType
    evidence_source_url: str
    evidence_locator: str | None = None
    evidence_text: str | None = None
    association_method: AssociationMethod
    observed_at: datetime

    @property
    def evidence_strength(self) -> int:
        return EVIDENCE_STRENGTH[self.evidence_type]


class GithubSnapshot(BaseModel):
    repo_url: str
    exists_verified: bool
    stargazers_count: int | None
    stars_fetched_at: datetime
    api_status: GithubApiStatus

    @field_validator("stargazers_count")
    @classmethod
    def stars_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("stargazers_count must be non-negative")
        return v


# ---------------------------------------------------------------
# Final export schema -- matches the assessment's Research Paper spec exactly
# ---------------------------------------------------------------
class ResearchPaperExport(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"
    source_name: str = "arxiv"
    source_url: str
    title: str
    authors: list[str]
    paper_url: str
    github_url: str | None
    github_stars: int | None
    published_date: str | None
    collectedAt: str
    github_stars_fetched_at: str | None = None
    github_evidence_type: str | None = None
