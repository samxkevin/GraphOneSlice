# GhostTrace Shared Progress

Last updated: 2026-10-25, ~14:00 IST. Deadline: 2026-10-25 18:00 IST (user-confirmed). Progress is evidence-based and does not imply external submission.

## Workstream ownership

| Owner | Files | Status | Verified evidence |
|---|---|---|---|
| Plus | `GhostTrace/code/main.py`, `code/ai_bridge.py` | Implemented | GitHub commits, CI unit tests |
| Plus | `code/evaluation/evaluate.py`, evaluator reports, `code/tests/test_core.py`, `test_models.py`, `test_endtoend.py` | Implemented | Measured 32 sample evaluation, automated tests |
| Plus | `.github/workflows/ghosttrace.yml`, `README.md`, `code/docs/`, packaging, integration | Implemented baseline | GitHub Actions 518-row schema validation and generated ZIP |
| Arena | `GhostTrace/code/evidence.py`, `code/tests/test_evidence.py`, `docs/EVIDENCE.md` | **Not yet delivered or verified** | Exact assignment in `ARENA_HANDOFF.md`; branch/PR to be supplied by Arena |
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
- 32 labelled samples: **29 status correct** (90.625%); exact sequence **8** (25%); 152 matched steps out of 156 predicted and 193 reference, precision 97.44%, recall 78.76%.
- Multi-model mock tests, synthetic adversarial tests, and end-to-end mini evidence tests added to CI. Do not claim live API tests.
- No hidden-label accuracy, production data completeness, image interpretation, or provider latency measured.

## Outstanding blockers and improvements

1. Arena's parser PR and actual tests are not yet available. Do not claim it is integrated.
2. PDF/image OCR and some unlinked deletion/anonymous verification proofs are missing from baseline. Sample sequence recall remains below ideal.
3. True transcript export: `log.txt` is a disclosed session summary, not the complete verbatim ChatGPT interaction. Obtain authentic export for the chat transcript slot if possible.
4. Deadline: the user must upload `code.zip`, `output.csv`, and a genuine transcript to HackerRank; **GitHub Actions publishing is not HackerRank submission**.
5. The challenge is an individual hackathon. Arena and Plus are AI coding tools directed by one participant, not separate human teammates.

## Next acceptance gates

- Arena supplies actual PR SHA, changed file list, tests and measured sample delta.
- Plus reviews code, integrates only if CI remains green, and confirms source traces and after-`audit_at` behavior.
- Re-run the whole workflow, retrieve GitHub Actions artifact, unzip and independently validate `output.csv`, source ZIP, and reports.
- Owner uploads before 18:00 IST and participates in the AI judge interview.
