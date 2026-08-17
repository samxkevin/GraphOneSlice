from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceClaim(BaseModel):
    field: str
    value: str | bool | None = None
    evidence_quote: str | None = None
    supported: bool = False


class ExtractionResult(BaseModel):
    company: str | None = None
    role_family: str | None = None
    is_remote: bool | None = None
    summary: str | None = None
    evidence_quotes: list[str] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)


class ReviewResult(BaseModel):
    corrected_extraction: ExtractionResult
    corrections: list[str] = Field(default_factory=list)
    added_information: list[str] = Field(default_factory=list)
    removed_information: list[str] = Field(default_factory=list)
    review_status: Literal[
        "ACCEPTED",
        "CORRECTED",
        "CONFLICT",
        "INSUFFICIENT_EVIDENCE",
    ]


class ProviderAttempt(BaseModel):
    provider: str
    model: str
    success: bool
    result: ExtractionResult | ReviewResult | None = None
    error: str | None = None


class PipelineResult(BaseModel):
    final_extraction: ExtractionResult | None = None
    gemini: ProviderAttempt | None = None
    cohere: ProviderAttempt | None = None
    groq: ProviderAttempt | None = None
    validation_status: Literal["VALIDATED", "QUARANTINE"]
    validation_errors: list[str] = Field(default_factory=list)