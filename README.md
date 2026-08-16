# GraphOne / FrontierAtlas — Research Paper Vertical Slice

First vertical slice for the AI Engineer assessment: **arXiv → deterministic
parsing → evidence-tiered GitHub association → GitHub star verification →
deterministic validation → PostgreSQL → Google Sheets export**.

Scope is deliberately narrow. YC, Product Hunt, News, and Jobs adapters and
the generic Gemini extraction layer are **not implemented here** — this
slice exists to prove the architecture end-to-end on the one fully-verified
integration path (see the evidence-closure record this project produced
before writing any code).

## Honest current status

**Actually run and passing in this environment: 55/55 unit/integration tests**
(44 from the prior pass + 11 new this pass: 5 for GitHub retry-exhaustion
classification, 5 for arXiv-Atom-to-paper lineage, 4 for abs-page-HTML
persistence — note some overlap/replacement of prior GitHub client tests,
see git history). Covers the parser, retry logic, repo associator,
validator, GitHub client, the abs-page HTML evidence extractor, the async
fetch adapter, an integration path feeding real extracted evidence into
the unmodified association engine, and now the two provenance-lineage
fixes (Atom fetch → paper linkage, abs-page HTML persistence). No test in
this suite makes a real network call — every HTTP-touching test uses
`httpx.MockTransport`, and lineage tests use an in-memory `FakeStorage`
test double instead of a live Postgres connection. Command used:

```bash
python -m pytest tests/ -v
```

**What this proves, precisely, and no more:**
- Component-level behavior (parsing, normalization, dedup, evidence
  provenance, retry/timeout/rate-limit classification, association
  tie-breaking, fetch-to-paper lineage linking) is verified against
  realistic offline HTML/Atom fixtures and mocked HTTP transports.
- `extract_authoritative_repo_links` is a real, deterministic component,
  wired into `orchestrator.run_repo_resolution`, exercised end-to-end
  against the *existing, unchanged* `RepoAssociator`.
- The two provenance gaps identified by code review — `fetch_observations.
  paper_id` staying NULL during arXiv discovery, and abs-page HTML being
  discarded after extraction — are now fixed and covered by tests that
  exercise the real orchestrator functions (`run_discovery_and_parse`,
  `run_repo_resolution`) against an in-memory storage double, not just
  unit tests of isolated helper functions.
- The GitHub client's retry-exhaustion classification bug (any exhausted
  retry defaulting to `RATE_LIMITED`, even a plain 500 or a network
  timeout) is fixed and covered by tests that specifically assert the
  final `api_status`, which the prior test suite did not do.

**What this does NOT prove — do not conflate the two:**
- **Live arXiv page retrieval is not yet proven.** The extractor's
  container selectors (`_CONTENT_CONTAINER_SELECTORS` in
  `repo_evidence_parser.py`) are a best-effort approximation of arXiv's
  real abs-page DOM, calibrated against fixtures I wrote, not against a
  live-fetched current arXiv page. This must be spot-checked against
  real HTML before trusting its recall/precision on real papers.
- **Live GitHub API integration remains unproven** as a full pipeline
  run, even though the GitHub client itself is separately
  component-tested (including the corrected retry classification).
- **Postgres and Google Sheets are still not live-proven** — no database
  or credentials are available in this environment. The `paper_
  fetch_observations` join table added this pass has never been executed
  against a real Postgres instance; its SQL has been reviewed carefully
  but not run.
- 55/55 passing component/integration-with-mocks tests is evidence about
  correctness of logic in isolation, including cross-module lineage
  logic exercised via a fake storage layer. It is **not** evidence that
  the live, externally-integrated pipeline produces correct output at
  scale — that remains a separate, not-yet-performed verification step.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, GITHUB_TOKEN, Sheets config
python -m pytest tests/ -v          # run this first — should be 55/55
python -m src.pipeline.orchestrator  # live run, requires the .env values above
```

Sheets export additionally requires a Google Cloud service-account JSON key
(path set via `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`), with that service
account's `client_email` added as an Editor on the target spreadsheet.

## Architecture

```
arxiv_adapter (fetch)
      ↓
fetch_observations (raw Atom evidence, append-only, never overwritten;
                     one row can legitimately hold many papers' data)
      ↓
arxiv_parser (deterministic, no LLM)
      ↓
papers (logical identity, arxiv_id unique)
      ↓ (linked via paper_fetch_observations -- many-to-many, since one
      ↓  Atom page fetch produces many papers)
paper_fetch_observations (join table: which observation(s) supplied which paper)
      ↓
repo_evidence_adapter (async fetch of the paper's abs page HTML)
      ↓
fetch_observations (raw HTML evidence, append-only, 1:1 via scalar paper_id --
                     genuinely one fetch per paper, unlike the Atom case above)
      ↓
repo_evidence_parser (deterministic HTML -> RepoLinkCandidate,
                       explicit links only, no title/name guessing)
      ↓
repo_association (evidence-tiered rule engine, no LLM, no popularity guessing
                   -- UNCHANGED by this work, verified via integration tests)
      ↓
paper_repo_links (0..N candidates per paper, ambiguity preserved)
      ↓
github_client (verify + live stargazers_count; retry-exhaustion now
               classified truthfully -- RATE_LIMITED only on direct
               evidence, ERROR otherwise)
      ↓
github_repo_snapshots (append-only verification history)
      ↓
validator (deterministic schema + business rules)
      ↓
validated_records (frozen export payload)
      ↓
sheets_exporter (idempotent full-tab rewrite)
```

`fetch_observations` now serves two genuinely different relationship
shapes to `papers`: many-to-many for the Atom discovery fetch (one page,
many papers — via the `paper_fetch_observations` join table) and 1:1 for
the abs-page HTML fetch (one paper, one fetch — via the table's own
scalar `paper_id` column). Using a join table only where the relationship
is actually many-to-many, and the existing scalar column where it's
genuinely 1:1, was a deliberate choice to avoid forcing one structure
onto two different facts.

Every stage is a separate module; `storage/db.py` is the only file that
touches the database. See inline docstrings in each module for the specific
invariant it enforces (no fabricated GitHub associations, no guessed star
counts, bounded retries everywhere, etc.).

## Known gaps / next work (in priority order)

1. **Live end-to-end audit** — run the pipeline against real arXiv/GitHub/a
   scratch spreadsheet and manually inspect at least one record from each of
   the 8 required outcome classes (explicit link, multiple candidates, no
   repo, verified repo, deleted repo, retry/rate-limit, validation failure,
   successful Sheets export). **Not yet done in this environment — this is
   the immediate next step.** This has not gotten easier or harder as a
   result of this pass's fixes; it remains untouched.
2. **arXiv abs-page DOM assumptions need live spot-checking.** The
   extractor's selectors were written against fixtures I authored, not
   against a currently-served real arXiv page. Before trusting extraction
   coverage numbers on a real batch, fetch several live abs pages, diff
   their actual DOM structure against `_CONTENT_CONTAINER_SELECTORS`, and
   adjust if arXiv's real markup differs.
3. **GitHub client's `_retry_after` callback** is a no-op placeholder —
   it doesn't yet parse `Retry-After`/`X-RateLimit-Reset` headers from the
   raised exception to use an exact wait time instead of computed backoff.
   Functionally safe (falls back to backoff+jitter) but not optimal.
   Explicitly deferred again this pass per instruction ("don't
   over-engineer Retry-After parsing in this turn").
4. **`paper_fetch_observations` and the abs-page-HTML persistence path
   have never run against a real Postgres instance.** The SQL and the
   storage-layer method were written carefully against the existing
   schema conventions, but only exercised via the in-memory `FakeStorage`
   test double in this environment — a live run is the actual proof,
   not yet performed.
5. YC, Product Hunt, News, Jobs adapters, and the generic
   `LLMProvider.extract()` layer for Gemini/Groq/DeepSeek — not started.
   `storage`, `validator`, and `exporter` are built generically enough that
   these plug in as new adapter + parser modules without touching this
   slice's code (see contract review delivered alongside this code).

## Configuration

All limits, timeouts, batch sizes, and retry parameters are environment
variables (`src/config/settings.py` / `.env.example`) — nothing is a magic
number buried in source code, per the assessment's scale-without-code-change
requirement.
