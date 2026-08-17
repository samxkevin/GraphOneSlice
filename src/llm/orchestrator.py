from __future__ import annotations

from .providers import (
    CohereProvider,
    GeminiProvider,
    GroqProvider,
)
from .schemas import (
    ExtractionResult,
    PipelineResult,
    ProviderAttempt,
    ReviewResult,
)


def validate_extraction(
    evidence: str,
    extraction: ExtractionResult,
) -> tuple[str, list[str]]:
    errors: list[str] = []

    for quote in extraction.evidence_quotes:
        if quote not in evidence:
            errors.append(
                f"Evidence quote not found in source: {quote!r}"
            )

    for claim in extraction.claims:
        if claim.evidence_quote is None:
            if claim.supported:
                errors.append(
                    f"Supported claim has no evidence quote: "
                    f"{claim.field}"
                )
            continue

        if claim.evidence_quote not in evidence:
            errors.append(
                f"Claim evidence quote not found in source: "
                f"{claim.field}"
            )

        if claim.supported and claim.value is None:
            errors.append(
                f"Supported claim has no value: {claim.field}"
            )

    non_null_fields = {
        "company": extraction.company,
        "role_family": extraction.role_family,
        "is_remote": extraction.is_remote,
        "summary": extraction.summary,
    }

    supported_fields = {
        claim.field
        for claim in extraction.claims
        if claim.supported
    }

    for field, value in non_null_fields.items():
        if value is not None and field not in supported_fields:
            errors.append(
                f"Non-null field has no supported claim: {field}"
            )

    if errors:
        return "QUARANTINE", errors

    return "VALIDATED", []


async def run_llm_pipeline(
    evidence: str,
    gemini: GeminiProvider,
    cohere: CohereProvider,
    groq: GroqProvider,
) -> PipelineResult:

    gemini_attempt: ProviderAttempt | None = None
    cohere_attempt: ProviderAttempt | None = None
    groq_attempt: ProviderAttempt | None = None

    # Stage 1: Gemini initial extraction
    try:
        draft = await gemini.extract(evidence)

        gemini_attempt = ProviderAttempt(
            provider=gemini.name,
            model=gemini.model,
            success=True,
            result=draft,
        )

    except Exception as exc:
        gemini_attempt = ProviderAttempt(
            provider=gemini.name,
            model=gemini.model,
            success=False,
            error=str(exc),
        )

        # Fallback: Cohere performs initial extraction.
        try:
            draft = await cohere.fallback_extract(evidence)

            cohere_attempt = ProviderAttempt(
                provider=f"{cohere.name}-fallback-extract",
                model=cohere.model,
                success=True,
                result=draft,
            )

            fallback_review = ReviewResult(
                corrected_extraction=draft,
                corrections=[],
                added_information=[],
                removed_information=[],
                review_status="INSUFFICIENT_EVIDENCE",
            )

        except Exception as fallback_exc:
            cohere_attempt = ProviderAttempt(
                provider=f"{cohere.name}-fallback-extract",
                model=cohere.model,
                success=False,
                error=str(fallback_exc),
            )

            return PipelineResult(
                final_extraction=None,
                gemini=gemini_attempt,
                cohere=cohere_attempt,
                groq=None,
                validation_status="QUARANTINE",
                validation_errors=[
                    f"Gemini extraction failed: {exc}",
                    f"Cohere fallback extraction failed: {fallback_exc}",
                ],
            )

        # Final adjudication still goes through Groq.
        try:
            final = await groq.adjudicate(
                evidence,
                draft,
                fallback_review,
                execution_mode="fallback",
            )

            groq_attempt = ProviderAttempt(
                provider=groq.name,
                model=groq.model,
                success=True,
                result=final,
            )

        except Exception as groq_exc:
            groq_attempt = ProviderAttempt(
                provider=groq.name,
                model=groq.model,
                success=False,
                error=str(groq_exc),
            )

            return PipelineResult(
                final_extraction=None,
                gemini=gemini_attempt,
                cohere=cohere_attempt,
                groq=groq_attempt,
                validation_status="QUARANTINE",
                validation_errors=[
                    f"Gemini extraction failed: {exc}",
                    "Cohere fallback extraction succeeded",
                    f"Groq adjudication failed: {groq_exc}",
                ],
            )

        status, errors = validate_extraction(
            evidence,
            final,
        )

        return PipelineResult(
            final_extraction=final,
            gemini=gemini_attempt,
            cohere=cohere_attempt,
            groq=groq_attempt,
            validation_status=status,
            validation_errors=[
                f"Gemini unavailable: {exc}",
                "Cohere fallback extraction used",
                *errors,
            ],
        )

    # Stage 2: Cohere reviews Gemini's extraction
    try:
        review = await cohere.review(
            evidence,
            draft,
        )

        cohere_attempt = ProviderAttempt(
            provider=cohere.name,
            model=cohere.model,
            success=True,
            result=review,
        )

    except Exception as exc:
        cohere_attempt = ProviderAttempt(
            provider=cohere.name,
            model=cohere.model,
            success=False,
            error=str(exc),
        )

        return PipelineResult(
            final_extraction=None,
            gemini=gemini_attempt,
            cohere=cohere_attempt,
            groq=None,
            validation_status="QUARANTINE",
            validation_errors=[
                f"Cohere review failed: {exc}"
            ],
        )

    # Stage 3: Groq performs final adjudication
    try:
        final = await groq.adjudicate(
            evidence,
            draft,
            review,
        )

        groq_attempt = ProviderAttempt(
            provider=groq.name,
            model=groq.model,
            success=True,
            result=final,
        )

    except Exception as exc:
        groq_attempt = ProviderAttempt(
            provider=groq.name,
            model=groq.model,
            success=False,
            error=str(exc),
        )

        return PipelineResult(
            final_extraction=None,
            gemini=gemini_attempt,
            cohere=cohere_attempt,
            groq=groq_attempt,
            validation_status="QUARANTINE",
            validation_errors=[
                f"Groq adjudication failed: {exc}"
            ],
        )

    # Deterministic validation
    status, errors = validate_extraction(
        evidence,
        final,
    )

    return PipelineResult(
        final_extraction=final,
        gemini=gemini_attempt,
        cohere=cohere_attempt,
        groq=groq_attempt,
        validation_status=status,
        validation_errors=errors,
    )