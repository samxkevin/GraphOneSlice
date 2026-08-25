# GraphOneSlice — AI Orbit Ingestion Vertical Slice

This repository originally contained a research-paper ingestion slice (`arXiv → repository evidence → GitHub verification → validation → storage/export`). That implementation is still present under the existing `src/adapters`, `src/parsers`, `src/pipeline`, `src/storage`, and related modules.

This pass adds a separate **AI Orbit Data Ingestion Pipeline vertical slice** under `src/ai_orbit/`. The new pipeline is built around the requested workflow:

```text
Discovery
→ Fetching / Extraction
→ Cleaning
→ Normalization
→ Entity Resolution / Deduplication
→ Classification
→ Relationship Mapping
→ Validation
→ JSON Storage
```

The implementation is intentionally conservative: source data is authoritative, LLMs are not used as factual sources, and missing facts stay missing rather than being filled from assumptions.

## Current implemented AI Orbit milestone

**Implemented and executed:** first real vertical slice.

Latest checked run:

```bash
.venv/bin/python run.py
.venv/bin/python -m pytest tests/ -q
```

Observed result from the generated `data/validation_report.json`:

- `29` valid entities
- `15` valid relationships
- `100%` provenance coverage for accepted entities
- validation status: `passed`
- validation failures: `0`
- source failures recorded, not hidden: `2`
- automated tests: `64 passed`

This is not a 250–300 record final corpus yet. It is the required first working vertical slice with real source-backed records.

## Repository audit summary

Before this change, the repository already had:

- a working research-paper pipeline focused on arXiv papers and GitHub repository evidence;
- PostgreSQL-oriented storage code;
- a deterministic parser/validator path for research paper records;
- source adapters for arXiv and repository evidence pages;
- GitHub API verification code;
- an existing provider-agnostic LLM orchestration layer under `src/llm/`;
- tests for the research-paper path.

Gaps relative to the AI Orbit request were:

- no common AI Orbit entity schema (`id`, `entity_type`, `name`, `description`, `url`, `categories`, `source`);
- no AI Orbit category-oriented JSON outputs;
- no `data/entities.json`, `data/relationships.json`, `data/entity_mapping_log.json`, or `data/validation_report.json`;
- no deterministic AI Orbit entity resolution/mapping log;
- no AI Orbit source feasibility output;
- no relationship graph for companies/tools/tasks/MCP;
- no tests for AI Orbit normalization, URL handling, deduplication, relationship validation, provenance validation, retry behavior, or source failure isolation.

The new AI Orbit code is therefore separate from, and does not overwrite, the existing research-paper implementation.

## AI Orbit architecture

New modules:

```text
run.py
  ↓
src/ai_orbit/pipeline.py
  ↓
src/ai_orbit/adapters/        source-specific discovery/fetching
src/ai_orbit/stages/          cleaning, normalization, resolution, classification, relationships, validation, storage
src/ai_orbit/utils/           URL normalization, stable identity, HTTP retry/failure classification
src/ai_orbit/models.py        common schemas and internal records
src/ai_orbit/config.py        environment-driven configuration
```

Pipeline stages:

1. **Source verification** — probes each configured source and records feasibility facts in `data/source_feasibility.json`.
2. **Discovery / extraction** — adapters fetch source-backed records and preserve raw observed fields in provenance.
3. **Cleaning** — trims strings, collapses whitespace, normalizes URLs, and de-duplicates categories.
4. **Normalization** — computes normalized names, normalized URLs, canonical keys, and stable UUIDv5 entity IDs.
5. **Entity resolution / deduplication** — merges entities by deterministic canonical URL or normalized name, and writes `data/entity_mapping_log.json`.
6. **Classification** — assigns categories and creates task entities only from observed topics or description phrases.
7. **Relationship mapping** — creates only evidence-backed relationships with source URLs and method names.
8. **Validation** — checks schema, required fields, provenance, URLs, unsupported categories/types, metadata shape, duplicate IDs, malformed relationships, and missing relationship endpoints.
9. **Storage** — writes deterministic JSON artifacts under `data/`.

## Sources actually used in the vertical slice

### GitHub API

- Access method: GitHub REST API over JSON.
- Endpoints used:
  - `https://api.github.com/search/repositories`
  - `https://api.github.com/orgs/{org}`
- Supplies:
  - repository/tool records;
  - repository metadata: stars, primary language, last updated timestamp, topics;
  - organization/company records where GitHub org descriptions are present;
  - relationship evidence from repository owner metadata;
  - task evidence from observed repository topics.
- Authentication: optional. `GITHUB_TOKEN` increases rate limits but is not required for the current small run.
- Observed pagination: `page` / `per_page`; `Link` headers are available for additional pages.
- Observed rate-limit headers are captured in `data/source_feasibility.json`.

### PyPI JSON API

- Access method: public JSON endpoint `https://pypi.org/pypi/{package}/json`.
- Packages used by default:
  - `openai`
  - `anthropic`
  - `groq`
  - `mistralai`
- Supplies:
  - AI SDK/tool records;
  - package metadata such as version, Python requirement, license when present, project URLs;
  - company/author observations from `author` and `author_email` fields;
  - `Company → develops → Tool` relationship evidence from PyPI author metadata.
- Authentication: not required.
- Pagination: single project document; releases are keyed by version.

### NPM Registry MCP packages

- Access method: NPM registry package JSON documents.
- Packages used by default:
  - `@modelcontextprotocol/server-filesystem`
  - `@modelcontextprotocol/server-memory`
  - `@modelcontextprotocol/server-sequential-thinking`
  - `@modelcontextprotocol/server-github`
- Supplies:
  - MCP server records;
  - MCP metadata: package name, version, bin field, deprecation notice when present, installation method as an observed npm/npx package mechanism;
  - task evidence from package descriptions;
  - `MCP → integrates_with → Tool` relationship for the GitHub MCP package, based on the package description naming the GitHub API.
- Authentication: not required.
- Pagination: not used for a single package document.

### Sources probed but not used for records

The pipeline deliberately probes these sources and records failures instead of fabricating fallback data:

- **Hugging Face Hub API** — `https://huggingface.co/api/models`
  - observed in this environment as a TLS/network failure;
  - no model records were generated.
- **OpenAI News RSS** — `https://openai.com/news/rss.xml`
  - observed in this environment as a TLS/network failure;
  - no news records were generated.

These failures are present in both `data/source_feasibility.json` and `data/validation_report.json`.

## Common entity schema

Every exported entity supports the requested common fields:

```json
{
  "id": "stable-generated-uuid",
  "entity_type": "string",
  "name": "string",
  "description": "string",
  "url": "string",
  "categories": ["string"],
  "source": {
    "name": "string",
    "url": "string"
  }
}
```

The implementation also includes:

- `metadata` for domain-specific fields;
- `provenance` for source record ID, source URL, observed fields, transformation steps, and fetch time.

Domain-specific metadata support exists for:

- repositories: `stars`, `primary_language`, `last_updated_timestamp`;
- MCP: `installation_method`, `runtime_requirements`, package/version/bin/deprecation fields;
- companies: `founding_year`, `industry_sector`, `headquarters` fields are present but remain `null` unless a source actually supports them;
- models: validator support exists for `license`, `modalities`, and `provider`, but the current run does not emit model records because Hugging Face was inaccessible and no replacement model source was used.

## Entity resolution

Entity resolution is deterministic and auditable.

Implemented rules:

- normalize URLs for stable identity comparisons;
- normalize names by trimming/case-folding and removing common organization suffixes;
- resolve `OpenAI`, `Open AI`, and `OpenAI, Inc.` to the same canonical key;
- prefer canonical URL identity for tools/repositories/MCP;
- use normalized-name identity for companies and tasks;
- merge duplicate candidates without changing stable IDs;
- write every raw-to-canonical decision to `data/entity_mapping_log.json`.

Example mapping-log fields:

- `raw_value`
- `canonical_value`
- `method`
- `confidence`
- `source_url`
- `raw_source_key`
- `canonical_id`
- `reason`

## Relationship graph

Output file: `data/relationships.json`.

Relationship types supported by validation:

- `develops`
- `solves`
- `integrates_with`
- `runs`
- `published_by`
- `hosts`

Relationships produced in the current vertical slice include:

- `Company → develops → Tool` from PyPI author metadata;
- `Repository/Tool/MCP → solves → Task` from observed GitHub topics or package description phrases;
- `MCP → integrates_with → Tool` from the NPM package description for `@modelcontextprotocol/server-github` naming the GitHub API.

Relationships are not created from guesses. Each relationship includes:

- canonical source and target entity IDs;
- evidence field/value or observed source value;
- source URL;
- method name;
- confidence.

## Validation

`data/validation_report.json` includes:

- total discovered/extracted/cleaned/normalized/deduplicated/classified;
- total relationships;
- valid/rejected counts;
- per-source counts;
- per-category counts;
- per-entity-type counts;
- provenance coverage;
- failure counts by type;
- source failures;
- source feasibility details;
- duplicate URL warnings.

Validation checks at least:

- missing required fields;
- missing provenance;
- invalid URLs;
- duplicate entity IDs;
- duplicate URLs, reported as warnings when different abstract/task records share a source URL;
- unsupported entity types/categories;
- invalid metadata shape;
- malformed relationships;
- relationships pointing to missing entity IDs;
- empty/suspicious records.

## Retry and failure strategy

The AI Orbit HTTP client is in `src/ai_orbit/utils/http.py`.

It distinguishes:

- HTTP `429` rate limiting;
- HTTP `413` payload too large;
- HTTP `404` not found;
- HTTP `403` forbidden;
- timeout;
- network failure;
- malformed JSON;
- generic HTTP errors.

Retries are bounded and use exponential backoff plus jitter. A source that fails verification is recorded and skipped; records from other usable sources continue through the pipeline.

## LLM usage

The AI Orbit vertical slice does **not** use an LLM for factual extraction. This is intentional because the selected APIs already provide structured evidence.

The repository still contains an existing provider-agnostic LLM orchestration layer in `src/llm/`, with structured extraction/review/adjudication concepts and bounded provider retries. That layer is separate from this AI Orbit run and is not claimed as the source of any AI Orbit entity facts.

## How to run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Optional: copy and edit env values. No secrets are required for the small vertical slice.
cp .env.example .env

.venv/bin/python run.py
```

Outputs are written to `data/`.

## How to test

```bash
.venv/bin/python -m pytest tests/ -q
```

Latest local result:

```text
64 passed
```

AI Orbit-specific tests cover:

- entity normalization (`OpenAI`, `Open AI`, `OpenAI, Inc.`);
- URL normalization;
- deduplication;
- provenance validation;
- relationship validation;
- schema/business validation;
- bounded retry behavior;
- source failure isolation.

## Generated artifacts

Required outputs:

- `data/entities.json`
- `data/relationships.json`
- `data/entity_mapping_log.json`
- `data/validation_report.json`

Additional useful outputs:

- `data/source_feasibility.json`
- `data/categories/*.json`

The category exports are derived from `data/entities.json` and are intended for convenience only.

## Configuration

Environment variables for the AI Orbit slice are listed in `.env.example`.

Important values:

- `AI_ORBIT_OUTPUT_DIR`
- `AI_ORBIT_HTTP_TIMEOUT_SECONDS`
- `AI_ORBIT_MAX_RETRY_ATTEMPTS`
- `AI_ORBIT_RETRY_BACKOFF_BASE_SECONDS`
- `AI_ORBIT_RETRY_BACKOFF_MAX_SECONDS`
- `AI_ORBIT_RETRY_JITTER_SECONDS`
- `AI_ORBIT_CA_BUNDLE`
- `AI_ORBIT_GITHUB_SEARCH_QUERY`
- `AI_ORBIT_GITHUB_SEARCH_LIMIT`
- `GITHUB_TOKEN` (optional)

No real credentials are committed.

## Implemented vs planned

### Implemented now

- Modular AI Orbit pipeline architecture.
- Real source verification.
- Source-backed ingestion from GitHub API, PyPI JSON API, and NPM registry.
- Explicit failure recording for Hugging Face and OpenAI RSS probes.
- Stable UUID generation.
- URL normalization.
- Entity normalization and deduplication.
- Entity mapping log.
- Category classification from observed source metadata.
- Evidence-backed relationship extraction.
- JSON storage artifacts.
- Validation report with metrics and failures.
- Automated tests for core logic.

### Planned / future work

- Expand from the first 29-record vertical slice toward the requested 250–300 record representative dataset.
- Add a usable model source once Hugging Face or another legitimate model API is accessible from the runtime environment.
- Add verified news, videos, robots, devices, personal, and creative/product-specific sources rather than fabricating those categories.
- Add model relationships such as `Company → develops → Model` and device relationships such as `Device → runs → Model` only when source evidence supports them.
- Improve duplicate URL policy for abstract task entities if a task ontology source is added.
- Add incremental caching if the dataset grows enough to justify avoiding repeated source calls.

## Known limitations

- The current run is a vertical slice, not the final 250–300 record corpus.
- Hugging Face and OpenAI RSS were probed but inaccessible in this environment; their failure is recorded and no records were synthesized.
- Company founding year, industry sector, and headquarters are not populated unless sources provide those exact facts.
- No model records are emitted in the current run.
- The current source mix intentionally favors APIs/registries that were actually reachable during implementation.
- Duplicate URL warnings appear where abstract task records use the source URL that supplied the observed task label.
- The existing research-paper pipeline remains in the repository and is separate from the AI Orbit JSON pipeline.
