# Arena Implementation Handoff: GhostTrace Evidence Workstream

Owner: Arena (second coding agent). Plus owns `GhostTrace/code/main.py`, `GhostTrace/code/evaluation/evaluate.py`, the GitHub workflow, integration, and final submission.

Repository: `samxkevin/GraphOneSlice`, base branch `ghosttrace-orchestrate-oct2026`, project root `GhostTrace/`. Create branch `arena/ghosttrace-evidence` from `ghosttrace-orchestrate-oct2026`. Do not edit `main`, original GraphOneSlice files, or files owned by Plus.

Read official challenge docs:
- https://github.com/interviewstreet/hackerrank-orchestrate-october26/blob/main/AGENTS.md
- https://github.com/interviewstreet/hackerrank-orchestrate-october26/blob/main/problem_statement.md
- https://github.com/interviewstreet/hackerrank-orchestrate-october26/blob/main/README.md
- https://github.com/interviewstreet/hackerrank-orchestrate-october26/tree/main/dataset

## Assignment: approximately 50% of implementation effort

Implement `GhostTrace/code/evidence.py` replacing/extending capabilities of existing `GhostTrace/code/evidence_base.py`. Own `GhostTrace/code/tests/test_evidence.py`, `GhostTrace/docs/EVIDENCE.md`, and optional source-specific helper files under `GhostTrace/code/parsers/`. Do not modify `GhostTrace/code/main.py` or the evaluator.

Required interface (no third-party type dependency):
```python
def extract_facts(dataset_dir: pathlib.Path) -> list[dict]:
    ...
```
Each dict:
```
{"evidence_id": "evidence_XX", "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
 "system_id": "account_service", "resource_id": "account_...",
 "category": "USER_PROFILE", "state": "ABSENT|PRESENT|REDACTED|ANONYMIZED|ACTIVE|DISABLED|BLOCKED",
 "refs": ["user_...", "email...", "old alias...", "phone...", "hash..."],
 "fields": {source-supported structured fields}, "confidence": 1}
```
`timestamp` must denote observation time; manifest `captured_at` MUST NOT be after the case cutoff when using the fact. If useful, add `captured_at` separately so Plus can enforce both timestamps. Never invent resource IDs or infer subject membership just from file co-location; use exact evidence joins.

### Parser requirements
1. Comprehensive JSON snapshot bundles, service exports (including nested profile_lookups, index_queries/hits, connectors, backup/restore, support and analytics), and per-resource structured records. Preserve provenance and user/email aliases.
2. SQLite-compatible SQL snapshots: execute each file in isolated in-memory SQLite DB, inspect all tables including primary, read, reporting, regional and failover replicas, keep contradictory replicas as separate observations (do not let an ABSENT primary erase a PRESENT replica). Do not execute external scripts or attach file paths.
3. Application logs: parse key-value records, trace_id request/response correlation, resource lookups, search hits, PII scans, integrations, backup/restores, and explicitly record successful readbacks vs mere operation initiation. Do not treat generic task SUCCESS as proof of deletion.
4. Plain text handovers and mixed-format records.
5. PDFs: extract text via normal PDF parser / pdftotext; only use OCR for scanned pages if text extraction fails and content is relevant.
6. Screenshots/images: image parsing with optional OCR or actual available vision model if configured; record extraction uncertainty and never assert a fact on OCR alone without validation; graceful degradation when optional dependencies missing.
7. Propagate historical IDs only via verified joins on `user_id`, aliases, resource IDs and trace IDs. Strictly avoid prefix and substring false matches between similar user identities.
8. Do not silently drop file-read failures; write a diagnostic log excluding sensitive data. Restrict reported evidence_id to supplied manifest IDs.

### Acceptance tests
- Evidenced absent account (readback rows=0) and PRESENT account in failover replica.
- Nested JSON export content with resource identity and compliant anonymized record.
- SQL primary vs failover drift where surviving replica is not overwritten.
- Shared support conversation vs attachment record category.
- Active connector and restoration restrictions.
- Post-audit evidence cannot change a pre-audit case.
- Decoy identities similar to target are not matched.
- All 32 labelled sample cases measurable by running `python GhostTrace/code/main.py --sample`; do not hardcode labels/case IDs, and do not use organizer-only ground truth.
- Include actual tests run, file diffs/commits, documented remaining gaps.

### Deliverable
Commit all Arena-owned files to `arena/ghosttrace-evidence` and open a PR into `ghosttrace-orchestrate-oct2026`. Report PR URL, head SHA, tests executed and failures, measured sample changes, and any interface issues. Do not claim code is merged until Plus verifies it.

Target: finish early enough for Plus to run GitHub Actions full dataset and package by the October 25, 2026 18:00 IST deadline.

Note: Official event is **individual participant**; AI coding agents are tools, not separate human teammates. Do not solicit outside human collaborative authorship contrary to event rules.
