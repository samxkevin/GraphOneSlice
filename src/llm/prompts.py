from __future__ import annotations

import json

from .schemas import ExtractionResult,ReviewResult


def gemini_prompt(
    evidence: str,
    execution_mode: str = "primary",
) -> str:
    mode_instruction = (
        "This is the normal Stage 1 extraction."
        if execution_mode == "primary"
        else
        "This is a fallback Stage 1 extraction because the normal "
        "primary provider was unavailable. Do not describe this as a review."
    )

    return f"""
You are Stage 1 of a factual information extraction pipeline.

{mode_instruction}

Your task is INITIAL FACTUAL EXTRACTION.

Extract facts from the ORIGINAL EVIDENCE and return exactly one JSON object
matching the ExtractionResult schema.

The objective is not to produce the most complete-looking answer.
The objective is to produce the most accurate answer that the evidence
actually supports.

SOURCE OF TRUTH

The ORIGINAL EVIDENCE is the sole source of truth.

Nothing else is evidence.

Do not use:
- outside knowledge
- memory
- assumptions
- guesses
- likely values
- common knowledge
- inferred relationships
- information from the schema
- information implied by field names
- information that merely appears reasonable

A fact must be supported by the ORIGINAL EVIDENCE itself.

STRICT EVIDENCE RULES

- Use ONLY the ORIGINAL EVIDENCE.
- Do not guess.
- Do not infer unsupported facts.
- Do not fill missing information.
- Do not turn implications into confirmed facts.
- Do not invent names, dates, numbers, URLs, organizations, relationships,
  locations, roles, or attributes.
- If a field is not explicitly supported, return null.
- If the evidence is ambiguous, return null unless the schema explicitly
  provides a valid way to represent that ambiguity.
- If the evidence contains conflicting information that cannot be resolved
  from the evidence itself, do not choose a value using outside knowledge.
- Missing information is preferable to unsupported information.
- Null is preferable to a guess.
- A conservative extraction is preferable to a speculative extraction.

FIELD RULES

company:
- Return the explicitly stated company or organization name.
- Do not infer the company from a domain, email address, URL, job title,
  product name, author name, or surrounding context unless the evidence
  explicitly identifies it as the company or organization.
- Otherwise return null.

role_family:
- Return the explicitly stated job role or role family.
- Do not infer a broader role from a more specific title unless the evidence
  itself supports that interpretation.
- Otherwise return null.

is_remote:
- Return true when the evidence explicitly says the position is remote,
  fully remote, remote-first, or an equivalent explicit remote arrangement.
- Return false when the evidence explicitly says the position is on-site,
  office-based, or otherwise explicitly non-remote.
- Return null when the evidence does not explicitly establish either case.
- Do not infer remote status from location, distributed-team language,
  flexible-work language, or absence of an office requirement unless the
  evidence explicitly establishes remote work.

summary:
- Write exactly ONE short factual sentence.
- Use only facts explicitly supported by the ORIGINAL EVIDENCE.
- Do not add background knowledge.
- Do not speculate.
- Do not introduce facts that are absent from the extracted fields.
- Do not repeat the same fact unnecessarily.
- Do not make the sentence stronger than the evidence.

evidence_quotes:
- Return exact short pieces of text copied from the ORIGINAL EVIDENCE.
- Do not paraphrase.
- Do not rewrite.
- Do not manufacture quotes.
- Do not combine unrelated pieces of evidence into a quote.
- Each quote must directly support one or more extracted fields.
- A quote must support the exact value being claimed, not merely a related
  concept.

claims:
- Create exactly one supported claim for EVERY non-null extracted field:
  company, role_family, is_remote, and summary.
- The claim's field must exactly match the extracted field.
- The claim's value must exactly match the extracted field value.
- Every supported claim MUST contain an evidence_quote.
- The evidence_quote MUST be copied exactly from the ORIGINAL EVIDENCE.
- Set supported to true only when the ORIGINAL EVIDENCE directly supports
  the claim.
- If a field is null, do not create a supported claim for that field.
- Never omit a supported claim for a non-null field.
- Never create a supported claim for a value that the evidence does not
  directly establish.

IMPORTANT

The evidence itself is:

{evidence}

For the evidence above, the expected structure is similar to this:

{{
"company": "Acme AI",
"role_family": "Machine Learning Engineer",
"is_remote": true,
"summary": "Acme AI is hiring a fully remote Machine Learning Engineer.",
"evidence_quotes": [
"Acme AI is hiring a Machine Learning Engineer.",
"The position is fully remote."
],
"claims": [
{{
"field": "company",
"value": "Acme AI",
"evidence_quote": "Acme AI is hiring a Machine Learning Engineer.",
"supported": true
}},
{{
"field": "role_family",
"value": "Machine Learning Engineer",
"evidence_quote": "Acme AI is hiring a Machine Learning Engineer.",
"supported": true
}},
{{
"field": "is_remote",
"value": true,
"evidence_quote": "The position is fully remote.",
"supported": true
}},
{{
"field": "summary",
"value": "Acme AI is hiring a fully remote Machine Learning Engineer.",
"evidence_quote": "Acme AI is hiring a Machine Learning Engineer.",
"supported": true
}}
]
}}

This example is only an illustration of the required structure.

Do not copy its values unless they appear in the ORIGINAL EVIDENCE.

FINAL VERIFICATION

Before returning the JSON, verify every field independently.

1. Is every non-null field explicitly supported by the ORIGINAL EVIDENCE?
2. Does every non-null field have exactly one supported claim?
3. Does every supported claim have an exact evidence quote?
4. Is every evidence quote copied verbatim from the ORIGINAL EVIDENCE?
5. Does each claim value exactly match its corresponding field value?
6. Is is_remote true or false only when the evidence explicitly establishes
   the corresponding condition?
7. Does the summary contain only evidence-supported information?
8. Did you accidentally infer, assume, or complete anything?
9. Did you add any information merely because it would make the result
   appear more complete?

If any non-null field cannot pass these checks, return that field as null
and omit its supported claim.

Return ONLY valid JSON matching the ExtractionResult schema.
Do not add any other fields.
Do not include explanations, reasoning, markdown, or commentary outside JSON.
""".strip()


def cohere_prompt(
    evidence: str,
    draft: ExtractionResult,
    execution_mode: str = "primary",
) -> str:
    draft_json = json.dumps(
        draft.model_dump(),
        ensure_ascii=False,
        indent=2,
    )

    if execution_mode == "primary":
        role_instruction = """
You are Stage 2 of a factual extraction pipeline.

Gemini produced an initial extraction.

Your job is to independently REVIEW AND CORRECT that extraction using the
ORIGINAL EVIDENCE.

Gemini may be wrong.

Do not trust Gemini merely because it produced a value.
"""
        task = "REVIEW AND CORRECT"
    else:
        role_instruction = """
You are performing a FALLBACK INITIAL EXTRACTION because the normal Stage 1
provider was unavailable.

There is no Gemini review to perform in this execution.

Extract directly from the ORIGINAL EVIDENCE.

Do not describe this execution as a Gemini review or as Stage 2 review.
"""
        task = "INITIAL EXTRACTION"

    draft_section = (
        f"""
GEMINI DRAFT:
{draft_json}
"""
        if execution_mode == "primary"
        else ""
    )

    return f"""
{role_instruction}

TASK: {task}

The ORIGINAL EVIDENCE is the sole source of truth.

MODEL OUTPUT IS NOT EVIDENCE.

EVIDENCE AUTHORITY

Only the ORIGINAL EVIDENCE can establish a factual value.

Gemini's output is a draft, not evidence.

Do not use:
- outside knowledge
- memory
- assumptions
- guesses
- likely values
- agreement between models
- reasoning from the draft itself

A value is valid only when the ORIGINAL EVIDENCE directly supports it.

EVIDENCE RULES

- Use only the ORIGINAL EVIDENCE.
- Do not guess.
- Do not infer unsupported facts.
- Do not fill gaps.
- Do not turn implications into facts.
- Do not manufacture evidence.
- Do not paraphrase evidence quotes.
- Do not combine unrelated evidence fragments to create support.
- A Gemini value must be removed if the ORIGINAL EVIDENCE does not support it.
- A Gemini value may be corrected only when the ORIGINAL EVIDENCE supports
  the correction.
- Missing information must remain null.
- Agreement with Gemini is not evidence.
- A plausible value is not necessarily a supported value.

EXTRACTION RULES

company:
- Keep the company name only when explicitly supported by the ORIGINAL
  EVIDENCE.
- Do not infer it from domains, URLs, email addresses, product names,
  locations, or surrounding context.

role_family:
- Keep the role only when explicitly supported.
- Do not broaden or reinterpret the role beyond what the evidence supports.

is_remote:
- true only when the evidence explicitly indicates remote work.
- false only when the evidence explicitly indicates non-remote or on-site
  work.
- otherwise null.
- Do not infer remote status from flexible-work language, team location,
  geographic distribution, or absence of office information.

summary:
- ONE short factual sentence.
- Only evidence-supported information.
- No repetition.
- No speculation.
- No background knowledge.
- Do not make the summary stronger than the evidence.

evidence_quotes:
- Exact short quotes copied from the ORIGINAL EVIDENCE.
- Quotes must directly support the associated facts.
- Never manufacture, paraphrase, or strengthen a quote.

claims:
- Create exactly one supported claim for EVERY non-null extracted field:
  company, role_family, is_remote, and summary.
- The claim's field must exactly match the extracted field.
- The claim's value must exactly match the extracted field value.
- Every supported claim MUST have an exact evidence_quote.
- The evidence_quote MUST be copied verbatim from the ORIGINAL EVIDENCE.
- supported=true only when the ORIGINAL EVIDENCE directly supports the claim.
- If a non-null field cannot be directly supported, set that field to null
  and omit its supported claim.
- Never omit a supported claim for a non-null field.

REVIEW FIELDS

corrections:
- List only meaningful factual corrections made to Gemini.
- Do not report cosmetic changes.
- Do not report unnecessary rewording as a factual correction.

added_information:
- List only facts missing from Gemini that are explicitly supported by the
  ORIGINAL EVIDENCE.
- Do not add information merely because it appears reasonable.

removed_information:
- List only facts removed because the ORIGINAL EVIDENCE does not support them.
- Unsupported values must be removed even when they appear plausible.

review_status:
- ACCEPTED when the draft is supported and no meaningful correction is
  required.
- CORRECTED when one or more evidence-supported corrections were made.
- CONFLICT when the ORIGINAL EVIDENCE itself contains unresolved conflicting
  facts.
- INSUFFICIENT_EVIDENCE when the ORIGINAL EVIDENCE does not support enough
  information for a reliable extraction.

FINAL REVIEW CHECK

Before returning JSON:

1. Check every non-null field against the ORIGINAL EVIDENCE.
2. Check every supported claim against the ORIGINAL EVIDENCE.
3. Check that every non-null field has exactly one supported claim.
4. Check that every claim value exactly matches its field value.
5. Check that every evidence quote is copied verbatim.
6. Remove unsupported Gemini values.
7. Do not retain a value merely because Gemini and the evidence appear
   generally consistent.
8. Do not introduce information from outside the evidence.
9. Preserve null whenever the evidence is insufficient.

If a field cannot pass these checks, set it to null and do not create a
supported claim for it.

OUTPUT

- Return ONLY valid JSON.
- Match the supplied ReviewResult schema exactly.
- Do not add extra fields.
- Do not explain your reasoning outside the JSON.

ORIGINAL EVIDENCE:
{evidence}

{draft_section}
""".strip()


def groq_prompt(
    evidence: str,
    gemini: ExtractionResult,
    cohere: ReviewResult,
    execution_mode: str = "primary",
) -> str:
    gemini_json = json.dumps(
        gemini.model_dump(),
        ensure_ascii=False,
        indent=2,
    )

    cohere_json = json.dumps(
        cohere.model_dump(),
        ensure_ascii=False,
        indent=2,
    )

    if execution_mode == "primary":
        role_instruction = """
You are Stage 3, the FINAL ADJUDICATION stage of a factual extraction
pipeline.

Gemini performed the initial extraction.
Cohere performed the independent review and correction.
You are the final factual gate.
"""
    else:
        role_instruction = """
You are performing a FALLBACK FINAL EXTRACTION because the normal
adjudication provider was unavailable.

Do not claim that you performed the normal Stage 3 adjudication.

The ORIGINAL EVIDENCE remains the sole source of truth.
"""

    return f"""
{role_instruction}

Your task is to produce the final factual extraction supported by the
ORIGINAL EVIDENCE.

This is the FINAL FACTUAL GATE.

The previous model outputs are suggestions only.

They are NOT evidence.

SOURCE OF TRUTH

The ORIGINAL EVIDENCE is the sole authority for every factual value.

Gemini and Cohere cannot make a fact true.

Two models agreeing on a claim does not make that claim supported.

A model-generated correction does not make that correction supported.

A value must survive independent verification against the ORIGINAL EVIDENCE.

STRICT ADJUDICATION RULES

- Use only the ORIGINAL EVIDENCE.
- Do not use outside knowledge.
- Do not use memory.
- Do not guess.
- Do not infer unsupported facts.
- Do not preserve a claim merely because Gemini and Cohere agree.
- Agreement between models is NOT evidence.
- Keep a model-generated value only when the ORIGINAL EVIDENCE directly
  supports it.
- Keep a Cohere correction only when the ORIGINAL EVIDENCE directly supports
  it.
- Add missing information only when explicitly supported by the ORIGINAL
  EVIDENCE.
- Remove unsupported, speculative, or hallucinated information.
- Do not use one model's reasoning as evidence for another model's claim.
- Do not allow a previous model to override the ORIGINAL EVIDENCE.
- When evidence is insufficient, use null.
- When the evidence is ambiguous, prefer null unless the schema explicitly
  supports the ambiguity.
- When the evidence contains an unresolved contradiction, do not resolve it
  using outside knowledge.

FIELD RULES

company:
- Return only an explicitly supported company or organization name.
- Do not infer it from URLs, domains, email addresses, product names,
  locations, or contextual clues.

role_family:
- Return only an explicitly supported job role or role family.
- Do not broaden or reinterpret the role without evidence.

is_remote:
- true only if the evidence explicitly states remote work.
- false only if the evidence explicitly states non-remote or on-site work.
- null if neither condition is explicitly established.
- Do not infer remote status from flexible-work language, geographic
  distribution, or absence of office information.

summary:
- ONE concise factual sentence.
- Use only facts directly supported by the ORIGINAL EVIDENCE.
- No repetition.
- No speculation.
- No background knowledge.
- Do not make the summary stronger than the evidence.

evidence_quotes:
- Exact short quotes copied from the ORIGINAL EVIDENCE.
- Each quote must directly support the associated factual claim.
- Never paraphrase.
- Never manufacture a quote.
- Never combine unrelated evidence fragments into a synthetic quote.

claims:
- Create exactly one supported claim for EVERY non-null extracted field:
  company, role_family, is_remote, and summary.
- The claim's field must exactly match the extracted field.
- The claim's value must exactly match the extracted field value.
- Every supported claim MUST contain an evidence_quote.
- The evidence_quote MUST be copied verbatim from the ORIGINAL EVIDENCE.
- supported=true only when the ORIGINAL EVIDENCE directly supports the claim.
- If a non-null field cannot be directly supported, set that field to null
  and omit its supported claim.
- Never omit a supported claim for a non-null field.

FINAL FACTUAL AUDIT

For EVERY non-null field:

1. Is the value explicitly supported by the ORIGINAL EVIDENCE?
2. Is the evidence quote sufficient to establish that exact value?
3. Does the claims array contain exactly one supported claim for that field?
4. Does that claim's value exactly match the field value?
5. Is the evidence quote copied verbatim from the ORIGINAL EVIDENCE?
6. Am I relying on Gemini or Cohere instead of the ORIGINAL EVIDENCE?
7. Did I accidentally infer, assume, broaden, or complete anything?

Before returning JSON, verify all of the following:

- Every non-null field has exactly one supported claim.
- Every supported claim has an exact evidence quote.
- Every evidence quote appears verbatim in the ORIGINAL EVIDENCE.
- Every claim value exactly matches its corresponding field value.
- No unsupported value remains non-null.
- No model agreement is being treated as evidence.
- No information from outside the ORIGINAL EVIDENCE has entered the result.
- The summary contains no unsupported information.

If any non-null field fails these checks, return that field as null and omit
its supported claim.

The goal is factual correctness, not completeness.

Missing information is acceptable.

Null is acceptable.

Unsupported information is never acceptable.

OUTPUT

- Return ONLY valid JSON.
- Match the supplied ExtractionResult schema exactly.
- Do not add extra fields.
- Do not include reasoning outside the JSON.
- Do not include markdown.
- Do not explain the decision.

ORIGINAL EVIDENCE:
{evidence}

GEMINI EXTRACTION:
{gemini_json}

COHERE REVIEW:
{cohere_json}
""".strip()