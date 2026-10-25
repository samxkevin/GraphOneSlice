# GhostTrace Shared Progress

Last updated: 2026-10-25, 16:30 IST. Deadline: 2026-10-25 18:00 IST (user-confirmed). Progress is evidence-based and does not imply external submission.

## Workstream ownership

| Owner | Files | Status | Verified evidence |
|---|---|---|---|
| Plus | `GhostTrace/code/main.py`, `code/ai_bridge.py` | Implemented | GitHub commits, CI unit tests |
| Plus | `code/evaluation/evaluate.py`, evaluator reports, `code/tests/test_core.py`, `test_models.py`, `test_endtoend.py` | Implemented | Measured 32 sample evaluation, automated tests |
| Plus | `.github/workflows/ghosttrace.yml`, `README.md`, `code/docs/`, packaging, integration | Implemented baseline | GitHub Actions 518-row schema validation and generated ZIP |
| Arena | `GhostTrace/code/evidence.py`, `code/tests/test_evidence.py`, `docs/EVIDENCE.md` | **Merged and verified** | PR #4, merge `ec1501227c625a0189a6fbce1521229147a36630`; `25` CI tests passed |
| Owner | Review, relay Arena prompt, upload to HackerRank, conduct 30-minute interview | Pending | Requires owner action |

### Integration contract

`code/main.py` tries `from evidence import extract_facts`; if unavailable, uses `from evidence_base import extract_facts`. Signature: `extract_facts(dataset_dir: pathlib.Path) -> list[dict]`. Fields: `evidence_id,timestamp,captured_at,system_id,resource_id,category,state,refs,fields`; any optional confidence must be numeric. Each fact must be independently supported by manifest-listed, actually-read evidence. Extra claims are not allowed.

### Source of truth

- Organizer-only canonical answers and generator internals have **not** been used.
- Live provider keys are not in the repository.
- The three-model adapter is disabled by default and only mock-tested; current measured model calls are zero.
- The YouTube walkthrough itself could not be accessed; source verification in `code/docs/video_review_access.md`.

## Latest measured performance

The most recent successful workflow, rather than README estimates, is authoritative. As of implementation baseline:

- 518 evaluation requests produce exactly 518 rows; schema/step-order/evidence-reference checks pass.
- 32 labelled samples: **29 status correct** (90.625%); exact sequence **8** (25%); 155 matched steps out of 159 predicted and 193 reference, precision 97.48%, recall 80.31%.
- Multi-model mock tests, synthetic adversarial tests, and end-to-end mini evidence tests added to CI. Do not claim live API tests.
- No hidden-label accuracy, production data completeness, image interpretation, or provider latency measured.

## Outstanding blockers and improvements

1. Arena's parser PR and actual tests are not yet available. Do not claim it is integrated.
2. PDF/image OCR and some unlinked deletion/anonymous verification proofs are missing from baseline. Sample sequence recall remains below ideal.
3. True transcript export: `log.txt` is a disclosed session summary, not the complete verbatim ChatGPT interaction. Obtain authentic export for the chat transcript slot if possible.
4. Deadline: the user must upload `code.zip`, `output.csv`, and a genuine transcript to HackerRank; **GitHub Actions publishing is not HackerRank submission**.
5. The challenge is an individual hackathon. Arena and Plus are AI coding tools directed by one participant, not separate human teammates.

## Next acceptance gates

- Arena delivered PR #4 (head `c2e2ad3ce739a5b9a49c7029ac05d05c0969d4f1`) and the parser is merged.
- Plus reviews code, integrates only if CI remains green, and confirms source traces and after-`audit_at` behavior.
- Re-run the whole workflow, retrieve GitHub Actions artifact, unzip and independently validate `output.csv`, source ZIP, and reports.
- Owner uploads before 18:00 IST and participates in the AI judge interview.

## Final candidate integration check (16:30 IST)

- Reviewed Arena PR #4: 3 added files, 352 insertion lines, five evidence unit tests and API contract. Merged into the integration branch; performed independent full suite.
- Fixed SQL foreign-keys handling, PDF-supported attachments, contact/restore readbacks, point-in-time replica tie handling, and added synthetic tests. Last complete suite: **25 passing tests**.
- Fixed a substantial request-intent issue without case-ID rules: Portuguese `exclusão` is deletion intent; explicit English negations and marketing-only removal are not. The 518-row dataset now produces exactly **10** non-deletion cases rather than incorrectly classifying 14 Portuguese requests as NOT_APPLICABLE.
- Final verified workflow: `40186968983` (green), artifact `12595914808`. Generated and independently parsed **518/518** predictions, all case IDs once, required header, sorted, valid JSON, consecutive numbering. Step matching on participant samples: 155/159 predicted, 155/193 reference; case status 29/32, exact sequences 8/32.
- Complete source ZIP includes `code/evidence.py`, `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`. No nested ZIP or dataset in source ZIP. Model provider calls are zero.
- Arena's code makes no claim to parse image pixels; no hidden canonical answer performance is claimed.
- `log.txt` remains a clearly disclosed session summary, not the verbatim coding transcript; actual upload to HackerRank has NOT happened.
