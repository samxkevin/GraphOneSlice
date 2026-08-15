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

**Actually run and passing in this environment: 27/27 unit tests**, covering
the parser, retry logic, repo associator, validator, and GitHub client
(against `httpx.MockTransport` — no live network calls made). Command used:

```bash
python -m pytest tests/ -v
```

**Not run in this environment** (no live Postgres, no arXiv/GitHub/Sheets
credentials available here): the live `orchestrator.run_pipeline()` end-to-end
flow against a real database and real APIs. The code is written and the
component-level tests exercise every stage's logic in isolation, but a true
live end-to-end run — including the required audit across all 8 outcome
classes on live data — has not actually been executed and should not be
assumed to work merely because it type-checks. **Do this before scaling up
the batch size.**

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, GITHUB_TOKEN, Sheets config
python -m pytest tests/ -v          # run this first — should be 27/27
python -m src.pipeline.orchestrator  # live run, requires the .env values above
```

Sheets export additionally requires a Google Cloud service-account JSON key
(path set via `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`), with that service
account's `client_email` added as an Editor on the target spreadsheet.

## Architecture

```
arxiv_adapter (fetch)
      ↓
fetch_observations (raw evidence, append-only, never overwritten)
      ↓
arxiv_parser (deterministic, no LLM)
      ↓
papers (logical identity, arxiv_id unique)
      ↓
repo_association (evidence-tiered rule engine, no LLM, no popularity guessing)
      ↓
paper_repo_links (0..N candidates per paper, ambiguity preserved)
      ↓
github_client (verify + live stargazers_count)
      ↓
github_repo_snapshots (append-only verification history)
      ↓
validator (deterministic schema + business rules)
      ↓
validated_records (frozen export payload)
      ↓
sheets_exporter (idempotent full-tab rewrite)
```

Every stage is a separate module; `storage/db.py` is the only file that
touches the database. See inline docstrings in each module for the specific
invariant it enforces (no fabricated GitHub associations, no guessed star
counts, bounded retries everywhere, etc.).

## Known gaps / next work (in priority order)

1. **Live end-to-end audit** — run the pipeline against real arXiv/GitHub/a
   scratch spreadsheet and manually inspect at least one record from each of
   the 8 required outcome classes (explicit link, multiple candidates, no
   repo, verified repo, deleted repo, retry/rate-limit, validation failure,
   successful Sheets export). Not yet done in this environment.
2. **`extract_authoritative_repo_links`** (in `arxiv_parser.py`) is a stub —
   it currently returns `[]` always. This means the pipeline as shipped will
   correctly, honestly resolve every paper to `github_url = null` until the
   abs-page scraping step (or a PapersWithCode enrichment adapter) is wired
   in to actually populate `paper_repo_links` candidates. This is
   intentional: the interface and every downstream stage is built and
   tested against synthetic candidates, but no live evidence-gathering
   step exists yet, so nothing is fabricated in the meantime.
3. **GitHub client's `_retry_after` callback** is a no-op placeholder —
   it doesn't yet parse `Retry-After`/`X-RateLimit-Reset` headers from the
   raised exception to use an exact wait time instead of computed backoff.
   Functionally safe (falls back to backoff+jitter) but not optimal.
4. YC, Product Hunt, News, Jobs adapters, and the generic
   `LLMProvider.extract()` layer for Gemini/Groq/DeepSeek — not started.
   `storage`, `validator`, and `exporter` are built generically enough that
   these plug in as new adapter + parser modules without touching this
   slice's code (see contract review delivered alongside this code).

## Configuration

All limits, timeouts, batch sizes, and retry parameters are environment
variables (`src/config/settings.py` / `.env.example`) — nothing is a magic
number buried in source code, per the assessment's scale-without-code-change
requirement.
