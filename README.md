# GraphOne / FrontierAtlas : Research Paper Vertical Slice

First vertical slice for the AI Engineer assessment: **arXiv → deterministic
parsing → evidence-tiered GitHub association → GitHub star verification →
deterministic validation → PostgreSQL → Google Sheets export**.

The Research Paper vertical slice has now been exercised on a **live 1,000-paper
run**, reaching validation and export successfully.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/samxkevin/GraphOneSlice/blob/main/LICENSE)
[![Google Sheet(EvidenceBackedResearchPapers)](https://img.shields.io/badge/Google%20Sheet-Live-blue?logo=google-sheets)](https://docs.google.com/spreadsheets/d/1SDXAOpoBfjw4FqSvanXcokHlRMkHdQb5lqb_ou9rKs4/edit?usp=sharing)

The implementation deliberately keeps source-specific processing separate.
YC, Product Hunt, News, Jobs, and Entity Resolution are separate assessment
areas and are not represented as completed results by this vertical slice.

## Current Status

### Live Research Paper Results

The completed live run produced:

- **1,000 research papers processed and validated**
- **1,000 research-paper records exported to Google Sheets**
- arXiv retrieval completed successfully
- arXiv abstract pages retrieved for repository evidence
- GitHub repositories verified through the GitHub API
- GitHub star counts recorded from API responses
- raw fetch observations and repository evidence persisted for provenance
- deterministic validation completed before export
- **55/55 automated tests passing**

The 1,000-paper result is a **live integration result**, not a mock or
fixture-only benchmark.

The implementation has **not** been benchmarked at 500,000 records.
The 500,000-record figure is an architectural scaling target, not a claim
about a completed 500,000-record run.

### What the Research Paper Slice Proves

The completed slice demonstrates an end-to-end research-paper path:

```text
arXiv
  ↓
deterministic parsing
  ↓
paper identity
  ↓
abstract-page evidence retrieval
  ↓
explicit GitHub repository evidence extraction
  ↓
evidence-tiered repository association
  ↓
GitHub API verification
  ↓
star-count observation
  ↓
deterministic validation
  ↓
PostgreSQL
  ↓
Google Sheets export
````

The repository association stage remains deterministic and evidence-based.
Repository popularity is not used to invent or select unsupported
paper-to-repository relationships.

Ambiguity is preserved rather than silently converted into a guessed
association.

## Automated Verification

**55/55 tests are passing** in the current test suite.

The suite covers the parser, retry logic, repository associator, validator,
GitHub client, abstract-page HTML evidence extraction, asynchronous fetch
adapter, and integration paths involving real extracted evidence and the
existing association engine.

The provenance-lineage fixes are also covered:

* arXiv Atom fetch observations are correctly linked to the papers extracted
  from them.
* abstract-page HTML evidence is persisted rather than discarded after
  extraction.
* the GitHub client's retry-exhaustion classification distinguishes actual
  rate-limit exhaustion from ordinary server errors and network timeouts.

HTTP-touching tests use `httpx.MockTransport`. Provenance-lineage tests use
an in-memory `FakeStorage` rather than requiring a live PostgreSQL connection.

Run:

```bash
python -m pytest tests/ -v
```

## LLM Orchestration

A separate evidence-grounded LLM pipeline is implemented for semantic
extraction and review.

The intended normal execution sequence is:

```text
same ORIGINAL EVIDENCE
        ↓
Gemini 3.7 Flash
initial extraction
        ↓
Cohere Command A+
review and correction
        ↓
Groq GPT-OSS 120B
final adjudication
        ↓
deterministic validation
        ↓
VALIDATED / QUARANTINE
```

The original evidence remains the authoritative source throughout the LLM
pipeline.

The models are not treated as independent sources of truth. A later model
may correct or add information only when the original evidence supports that
change.

Agreement between models is **not** treated as evidence.

The implementation distinguishes normal provider execution from fallback
execution so that an audit record does not incorrectly describe a fallback
extraction as a normal review or adjudication stage.

### LLM Live Test Status

The fallback path has been exercised successfully:

* Gemini 3.7 Flash returned HTTP 429 after retries.
* Cohere successfully performed the fallback extraction.
* Groq GPT-OSS 120B successfully performed final adjudication.
* Deterministic evidence validation returned `VALIDATED`.

The normal:

```text
Gemini → Cohere → Groq
```

three-stage path is implemented, but the complete normal three-provider path
has **not** been live-proven because Gemini was rate-limited during the live
test.

This distinction is intentional. The repository does not claim a successful
normal three-provider execution that was not actually observed.

The LLM pipeline is also kept separate from the deterministic Research Paper
vertical slice. The 1,000-paper Research Paper result should therefore not be
interpreted as a claim that every one of those records passed through the
Gemini → Cohere → Groq pipeline.

## What Is Live-Proven vs. What Is Not

### Live-proven in the Research Paper vertical slice

* 1,000-paper live run
* arXiv retrieval
* deterministic paper parsing
* paper identity handling
* abstract-page retrieval
* explicit repository evidence extraction
* evidence-tiered repository association
* GitHub API verification
* GitHub star-count retrieval
* PostgreSQL persistence
* raw evidence/provenance persistence
* deterministic validation
* Google Sheets export
* 55/55 automated tests

### Implemented and separately exercised, but not part of the

1,000-paper live-path claim

* evidence-grounded LLM orchestration
* provider retry and fallback handling
* Gemini initial extraction
* Cohere review/fallback extraction
* Groq final adjudication
* deterministic validation of the LLM result

### Not completed as live assessment datasets

* Startup collection at 1,000+ records
* Product collection at 1,000+ records
* News collection covering the required 24-hour window
* Jobs collection covering the required 24-hour window
* Entity Resolution / Entity Mapping Log
* full 500,000-record production run
* production-scale anti-bot infrastructure

These areas are intentionally not represented as completed live results.

## Assessment Scope

The Research Paper vertical slice is deliberately narrow.

Its purpose is to prove the architecture end-to-end on the research-paper
path where the source and integration behavior have been verified.

The remaining source-specific adapters are kept separate so that their
feasibility and failure modes can be evaluated independently rather than
being hidden behind the Research Paper result.

The current assessment status is:

| Assessment area                 | Status                                     |
| ------------------------------- | ------------------------------------------ |
| Research Papers                 | **Live-proven: 1,000 records**             |
| GitHub repository evidence      | **Live-proven**                            |
| GitHub star verification        | **Live-proven**                            |
| PostgreSQL persistence          | **Live-proven**                            |
| Google Sheets export            | **Live-proven**                            |
| Deterministic validation        | **Live-proven**                            |
| LLM orchestration               | **Implemented; fallback path live-tested** |
| Startups                        | Not completed                              |
| Products                        | Not completed                              |
| News                            | Not completed                              |
| Jobs                            | Not completed                              |
| Entity Resolution / Mapping Log | Not completed                              |
| 500,000-record run              | Not performed                              |

## Architecture

```text
arxiv_adapter (fetch)
      ↓
fetch_observations
(raw Atom evidence, append-only)
      ↓
arxiv_parser
(deterministic, no LLM)
      ↓
papers
(logical identity, arxiv_id unique)
      ↓
paper_fetch_observations
(many-to-many lineage:
 one Atom fetch can contain many papers)
      ↓
repo_evidence_adapter
(async fetch of paper abs-page HTML)
      ↓
fetch_observations
(raw HTML evidence, append-only;
 1:1 via scalar paper_id)
      ↓
repo_evidence_parser
(deterministic HTML → RepoLinkCandidate;
 explicit links only)
      ↓
repo_association
(evidence-tiered deterministic rule engine)
      ↓
paper_repo_links
(0..N candidates per paper;
 ambiguity preserved)
      ↓
github_client
(verify repository + live stargazers_count)
      ↓
github_repo_snapshots
(append-only verification history)
      ↓
validator
(deterministic schema + business rules)
      ↓
validated_records
(frozen export payload)
      ↓
sheets_exporter
(idempotent full-tab rewrite)
```

`fetch_observations` serves two genuinely different relationship shapes to
`papers`:

1. **Many-to-many** for the arXiv Atom discovery fetch, because one fetched
   Atom response can contain many papers. This relationship is represented by
   `paper_fetch_observations`.
2. **1:1** for the abstract-page HTML fetch, because the fetch is associated
   with a specific paper through the scalar `paper_id`.

The implementation therefore uses a join table where the relationship is
actually many-to-many and the existing scalar relationship where it is
actually 1:1.

Every stage is a separate module.

`storage/db.py` is the database access boundary.

The deterministic repository-association engine does not use an LLM to guess
a repository from a paper title, repository popularity, or unrelated
similarity.

## Evidence and Provenance

Raw source evidence is persisted rather than discarded after parsing.

The research-paper path maintains provenance through:

* raw arXiv Atom observations
* paper-to-fetch lineage
* raw abstract-page HTML observations
* explicit repository-link candidates
* repository association results
* GitHub verification snapshots
* deterministic validation results
* frozen export payloads

This allows downstream decisions to be traced back to the evidence from which
they were derived.

A source observation and the paper extracted from that observation are not
assumed to have a 1:1 relationship. The lineage model reflects the actual
shape of the source response.

## Deterministic Repository Association

Repository association is intentionally conservative.

The system extracts explicit repository evidence from the paper's available
evidence and applies an evidence-tiered deterministic association process.

The association engine does not:

* invent repository URLs
* select a repository merely because it has the highest GitHub stars
* use repository popularity as evidence of a paper relationship
* silently discard ambiguity
* use outside knowledge to manufacture an association

Multiple supported candidates can remain associated with a paper rather than
forcing an unsupported single choice.

## GitHub Verification

GitHub verification is performed through the GitHub API.

The client records repository verification observations, including the
observed star count.

Retry behavior distinguishes different failure classes rather than treating
every exhausted retry as a rate-limit event.

In particular:

* HTTP 429 is treated as rate limiting.
* retryable 5xx responses are retried separately.
* network and timeout failures are handled separately.
* HTTP 413 is treated as a request-payload-size failure.
* retry exhaustion preserves the actual failure classification.

The current retry-after callback remains a deferred optimization: the client
can fall back to computed backoff and jitter rather than requiring exact
`Retry-After` or `X-RateLimit-Reset` parsing.

## Deterministic Validation

LLM output and extracted source data do not become exportable merely because
a model produced them.

The deterministic validator applies the schema and business rules before
records reach the export stage.

The resulting validated record is then frozen as the export payload.

The principle is:

```text
model output
    ↓
evidence validation
    ↓
business validation
    ↓
VALIDATED / QUARANTINE
    ↓
export
```

This keeps model behavior separate from the final acceptance decision.

## Scaling Design

The current Research Paper implementation is designed so that increasing the target record count does not require changing application logic.

The design uses:

* paginated source retrieval
* configurable request delays
* bounded asynchronous concurrency
* PostgreSQL as the system of record
* idempotent state transitions
* persisted raw evidence
* append-only fetch and verification observations
* deterministic validation before export
* provider retry and fallback handling
* structural rechunking for HTTP 413 responses
* retry-after/backoff handling for HTTP 429 responses

For a larger deployment, work can be claimed atomically from PostgreSQL and
processed by bounded workers.

A separate message broker is not required as the first scaling step.

The **500,000-record figure is an architectural target**, not a claim that
the current implementation has processed 500,000 records.

The 1,000-paper live result demonstrates the current integration path; it does
not by itself constitute a 500,000-record performance benchmark.

## Known Limitations

### arXiv abstract-page DOM

The abstract-page evidence extractor uses the configured content-container
selectors in `repo_evidence_parser.py`.

The selectors were calibrated against the available fixtures. Additional live
spot-checking of currently served arXiv HTML remains appropriate before using
the extractor's observed coverage as a production recall/precision claim.

### GitHub Retry-After Precision

The GitHub client's `_retry_after` callback remains a no-op placeholder.

The current behavior remains functionally safe because the client can fall
back to computed backoff and jitter, but exact parsing of
`Retry-After` / `X-RateLimit-Reset` remains an optimization.

### Live PostgreSQL Coverage of the New Lineage Path

The provenance-lineage behavior has been exercised through the in-memory
`FakeStorage` test double.

The corresponding live PostgreSQL behavior for the newly added
`paper_fetch_observations` path and abstract-page HTML persistence should not
be claimed beyond the live evidence actually obtained.

### Broader Assessment Sources

The Research Paper vertical slice does not constitute completion of the
Startup, Product, News, Jobs, or Entity Resolution portions of the assessment.

Those remain separate workstreams.

## Remaining Work

The remaining assessment work is:

1. Startup collection and validation at 1,000+ records.
2. Product collection and strict AI-product filtering at 1,000+ records.
3. Fresh News collection covering the required 24-hour window.
4. Fresh Jobs collection covering the required 24-hour window.
5. Entity resolution and the final Entity Mapping Log.
6. Production-grade anti-bot and large-scale crawling infrastructure.
7. Further live validation of source-specific behavior where not yet proven.
8. Larger-scale performance testing beyond the completed 1,000-paper run.

These items are not hidden behind the Research Paper result.

## Setup

```bash
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Fill in DATABASE_URL, GITHUB_TOKEN, and Sheets configuration.

python -m pytest tests/ -v
```

The automated test suite should currently report:

```text
55 passed
```

A live pipeline run requires the configured environment values:

```bash
python -m src.pipeline.orchestrator
```

Google Sheets export additionally requires a Google Cloud service-account
JSON key, with its path configured through
`GOOGLE_SERVICE_ACCOUNT_JSON_PATH`.

The service account's `client_email` must have Editor access to the target
spreadsheet.

## Configuration

All limits, timeouts, batch sizes, concurrency limits, and retry parameters
are configured through environment variables in
`src/config/settings.py` / `.env.example`.

The intention is to avoid embedding operational limits as magic numbers in
the source code and to allow deployment-specific scaling without changing
application logic.

## Design Principles

The implementation follows a small number of strict principles:

### Evidence before inference

Source evidence is preserved before downstream interpretation.

### Deterministic where deterministic is sufficient

The Research Paper path uses deterministic parsing and association wherever
the source provides structured or explicit evidence.

### LLMs are not sources of truth

When LLMs are used for semantic extraction, the original evidence remains
authoritative.

### Validation is independent of model confidence

A model saying that something is correct does not make it correct.

### Preserve uncertainty

When evidence does not establish a fact, the system should preserve the
uncertainty rather than manufacture a value.

### Provenance is part of the data

Raw evidence, fetch lineage, repository evidence, and verification
observations are retained so that downstream decisions can be traced back to
their source.

### Honest status reporting

Live-tested behavior, mocked/in-memory-tested behavior, implemented
architecture, and future scaling targets are kept explicitly separate.

The repository therefore does not use the 1,000-paper result, the LLM
fallback test, or the 500,000-record architecture as evidence for claims that
were not actually demonstrated.

[Google Sheet(EvidenceBackedResearchPapers)](https://docs.google.com/spreadsheets/d/1SDXAOpoBfjw4FqSvanXcokHlRMkHdQb5lqb_ou9rKs4/edit?usp=sharing)
