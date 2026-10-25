# GhostTrace: 30-minute AI Judge Technical Briefing

**Challenge**: HackerRank Orchestrate October 2026, Ghost Data Still Exists.  
**Implementation**: `GhostTrace/` in `samxkevin/GraphOneSlice` branch `ghosttrace-orchestrate-oct2026`.  
**Status at audit**: A real 518-row CSV was generated and re-parsed successfully. Unit tests passed. Participant-sample status accuracy 29/32 (90.625%); exact six-field step match precision 155/159 (97.4843%), recall 155/193 (80.3109%); exact ordered sequence 8/32 (25%). These figures are **participant-sample only**, not hidden evaluation accuracy.

## Problem, mission and why this architecture

The business problem is not just classification. A deletion status can be labelled COMPLETE while personal information remains in a secondary store, old alias, replica, export, analytic profile, support ticket, cache, index, backup, or active connector. Conversely, mandatory security and legal records must not be destroyed. The agent must distinguish request authorization, identity, observed state at `audit_at`, applicable retention policy, and reproducible evidence.

We selected GraphOneSlice as a **pattern library**, not a drop-in code dependency. Its implemented approach uses source-referenced records, extraction, normalization, entity resolution, deduplication, deterministic schema validation, and exact quote checking. We inspected `src/llm/providers.py`, `orchestrator.py`, `schemas.py`, and `prompts.py` instead of claiming every README feature was live.

## The verified GraphOneSlice three-model chain

1. **Google Gemini `gemini-3.7-flash`**: initial source-only structured extraction into Pydantic `ExtractionResult` with evidence quotes, claims, supported flags, and nullable fields.
2. **Cohere `command-a-plus-05-2026`**: stage-two review of Gemini draft, correction, conflict and unsupported-field detection; can perform fallback extraction.
3. **Groq serving `openai/gpt-oss-120b`**: evidence-grounded final adjudication of draft and review.

`validate_extraction` rejects purported quotes not present literally in the source, missing supported claims, and unsupported non-null values. HTTP client retries 429/5xx/timeouts with backoff; provider errors can cause quarantine rather than inventing facts. This chain is specialized to GraphOneSlice extraction fields `company,role_family,is_remote,summary` and **was not copied or invoked in the GhostTrace final run**. No provider credentials were available in CI. The GhostTrace submission adapts *its source-first design pattern* using a deterministic Python pipeline, with **zero model calls**; usage report states this clearly. Adding unsupported model steps would have made accuracy/cost/reproducibility worse for structured logs and SQL.

## Data and evidence graph

`code/evidence_base.py` reads manifest-identified JSON service exports and nested record bundles, SQLite SQL snapshots including replicas, log events and trace correlations, TXT handovers, and PDF text via `pdftotext`. Evidence facts use source `evidence_id`, observation `timestamp`, manifest `captured_at`, `system_id`, `resource_id`, `category`, `state`, exact subject references and optional fields. It does **not** currently reliably parse pixels of screenshot evidence; absence of readable PDF/OCR is a documented gap.

`code/main.py` resolves current and historical aliases via `user_identities.csv` and `user_audit_log.csv`. It compares exact normalized IDs, emails, hashes and phones, not fuzzy substrings. It gathers referenced facts; chooses the most recent recognized observation for a specific system/resource; rejects observations and capture times after `audit_at`. Status flags from the deletion workflow and `system_activity.csv` are **not** accepted as proof of absence. Database primary and failover replicas are separately ingested; without a verified resource identity an absent row in a snapshot cannot legitimately be inferred merely from a missing name.

`deletion_rules.csv` determines whether category treatment is DELETE, REDACT, ANONYMIZE or RETAIN. Backups are retained but must have unsafe restore blocked. Active data sync must be disabled. Tombstones preserve a stable user reference but redact direct identifiers. A passed readback can produce VERIFICATION; surviving prohibited data produces FINDING and proposed REMEDIATION before VERIFICATION. Proposed fixes use an empty evidence reference. The deterministic validator checks exact operation order and all seven required fields.

## What the measurements actually show

The participant labels are 32 cases. CI ran the 25 implemented unit tests including adversarial false-COMPLETE primary status, an old-email identity match, active restore blocking, future evidence filtering, explicit retention, non-deletion intent and multilingual classification. Test failures are not concealed: the first run failed French `suppression` matching, corrected. Initial sample status accuracy was 17/32 (53.125%). A JSON parser error dropped whole JSON files when a non-`hits` resource lacked that key. Fixing that restored structured evidence coverage; after additional policy and log parser fixes, the latest measured status score reached 29/32 (90.625%). The 518 evaluation rows are schema-valid, but hidden correctness is unknown. After examining the complete participant request list, we corrected Portuguese `exclusão` deletion intent and explicit English negations/marketing-only removal. This changed non-deletion predictions from an erroneous 19 to 10 while preserving the 29/32 sample status score; there are no hidden correctness labels.

Remaining errors come from **evidence recall and linkage**, especially absent accounts and anonymized profiles whose readbacks contain no customer identifier, PDF/image-only evidence and sparse log context. Synthetic or hardcoded expected resource IDs would be unacceptable. Exact sequence accuracy is only 25%; do not describe the agent as fully solved.

## What would improve this in production

Use an authorized full-fidelity evidence capture inventory with auditable stable resource IDs; propagate identity linking through request/trace IDs with defensible source provenance; add robust vision/OCR for supplied screenshots/scanned PDFs; include replica topology and state confidence instead of blindly preferring one record; retain raw evidence under privacy controls; add per-source parser tests, uncertainty quarantine and data minimization. Monitor false COMPLETE decisions, unsupported evidence cites, incomplete remediation steps, parse failures, model costs and system latency.

## Cost

The final measured execution invoked **no external AI models**: Google Gemini 0 calls, Cohere 0 calls, Groq 0 calls; input and output model tokens 0 and model-provider charges $0. It did consume GitHub Actions compute (not included in zero-dollar provider figure). The documented GraphOneSlice models were inspected, not silently used.

## Interview questions and suggested explanations

**Why not trust the workflow status?** `reported_status` describes intent or process outcome, not independent readback state. Replica drift and rehydration may contradict it.

**How are older identifiers found?** Exact current snapshot + both sides of field change events linked by stable user ID; evidence references propagate only through actual identifiers and verified resource IDs.

**What is audit_at?** The snapshot cutoff; later observations cannot retroactively fix earlier incomplete deletion.

**What if evidence is missing?** Do not assert ABSENT. Mark uncertain where supported; this reduces recall versus guesses but protects from false COMPLETE outcomes.

**Why not use a giant LLM for every record?** The output is strict schema and stable policy order. Deterministic evaluation is cheaper, testable, and handles SQL/JSON exactly. Models would help only with unstructured ambiguous evidence and must be citation checked.

**Did you reuse three live providers?** No. The prior project uses them but this implementation used their validation principles without API calls. The difference is disclosed in code and usage report.

**What was not implemented?** Direct screenshot visual understanding, full PDF OCR robustness, live paid provider multimodal inference, exact linkage of all source-less absence readbacks, and hidden dataset benchmarking.

**Was another human team member involved?** The event is individual. Arena is a separate AI coding assistant under the same entrant's supervision; no result should be claimed for Arena until a real PR and tests are inspected.
