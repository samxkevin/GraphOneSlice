# GraphOneSlice : AI Orbit Ingestion Continuation

This repository now contains **two distinct ingestion workstreams**. They share engineering principles, but their outputs must not be conflated.

[![              Python 3.12              ](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![              License: MIT              ](https://img.shields.io/badge/License-MIT-CE8837?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](https://github.com/samxkevin/GraphOneSlice/blob/main/LICENSE)
[![              Google Sheet              ](https://img.shields.io/badge/Google_Sheet-Live_Data-34A853?style=for-the-badge&logo=google-sheets&logoColor=white)](https://docs.google.com/spreadsheets/d/1SDXAOpoBfjw4FqSvanXcokHlRMkHdQb5lqb_ou9rKs4/edit?usp=sharing)    

## Workstream A : existing research-paper pipeline

The original repository workstream predates the AI Orbit JSON pipeline. It remains in the existing modules under `src/adapters`, `src/parsers`, `src/pipeline`, `src/storage`, `src/validator`, and related packages.

It has demonstrated the research-paper path:

```text
arXiv
→ deterministic parsing
→ abstract-page repository evidence extraction
→ evidence-backed GitHub repository association
→ GitHub API/star verification
→ deterministic validation
→ PostgreSQL persistence
→ Google Sheets export
```

The live 1,000-paper research-paper run is **separate** from the newer AI Orbit pipeline. The repository does not claim that those 1,000 research-paper records passed through the AI Orbit entity graph or through the LLM review chain.

## Workstream B : AI Orbit ingestion pipeline

The AI Orbit pipeline lives under `src/ai_orbit/` and implements:

```text
Discovery
→ Fetch / Extraction
→ Cleaning
→ Normalization
→ Entity Resolution / Deduplication
→ Classification
→ Relationship Mapping
→ Validation
→ JSON Storage
```

The implementation is deliberately conservative: source records are authoritative, LLM output is not used as factual evidence for these structured sources, and missing facts remain missing rather than being inferred.

## Current verified AI Orbit baseline

Latest verification commands run in this branch:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run.py
```

Current generated artifacts report:

- valid entities: `148`
- valid relationships: `50`
- validation status: `passed`
- validation failures: `0`
- rejected records: `0`
- provenance coverage: `100%`
- recorded source failures: `13`
- duplicate/shared URL warnings: `4`
- test result: `85 passed`

This is still an assessment vertical slice / early expansion, not the final 250–300 record representative corpus.

## Verification status labels

- **LIVE VERIFIED**: The current AI Orbit run has live-verified GitHub API, PyPI JSON API, NPM registry MCP package documents, NPM search/package documents, official SDK model definition ingestion, AI Tools List product-directory ingestion, Models.dev GitHub model-catalog ingestion, and ROS Robots Catalog ingestion. The latest executed run produced the counts above.
- **IMPLEMENTED BUT NOT LIVE-VERIFIED**: No additional accepted AI Orbit source adapter is claimed beyond the sources listed as live verified. Candidate probes may be implemented without accepted records.
- **UNIT/MOCK TESTED**: HTTP retry boundaries, source failure isolation, entity normalization/resolution, validation behavior, official SDK literal parsing, NPM relevance filtering, NPM category quality gates, Product quality gates, Models.dev metadata filtering, ROS robot catalog filtering, and task mapping guardrails are covered by automated tests.
- **PLANNED**: Broader product coverage beyond the bounded sample, plus news, jobs, videos, devices, and personal records remain planned until accessible sources prove the required identity and timestamp/metadata fields.
- **ARCHITECTURAL TARGET**: The long-term 250–300 record representative corpus remains a quality target, not a row-count target; no synthetic data is used to fill gaps.

## Repository audit and current implementation status

Before the AI Orbit work, the repository already had a working research-paper pipeline with arXiv, GitHub verification, PostgreSQL persistence, deterministic validation, and tests.

The AI Orbit implementation added and now maintains:

- common entity schema with stable IDs;
- modular source adapters;
- deterministic cleaning and normalization;
- deterministic entity resolution and deduplication;
- stable UUIDv5 identities;
- entity mapping log generation;
- controlled task classification from observed source values;
- evidence-backed relationship generation;
- deterministic validation report;
- source-feasibility reporting;
- required JSON outputs under `data/`;
- automated tests for AI Orbit behavior.

Entity resolution is therefore **implemented and tested for the current vertical slice**. What remains incomplete is assessment-scale entity mapping coverage across the full 250–300 record target and across additional source families.

## AI Orbit source adapters and probes

### Implemented ingestion adapters

#### GitHub API

- Access: GitHub REST JSON API.
- Used for: repositories/tools and company/org observations.
- Endpoints:
  - `https://api.github.com/search/repositories`
  - `https://api.github.com/orgs/{org}`
- Supplies source-backed repository metadata:
  - `full_name`
  - `html_url`
  - `description`
  - `owner`
  - `stargazers_count`
  - `language`
  - `updated_at`
  - `topics`
- Relationship evidence:
  - repository owner metadata for company/repository ownership when the owner entity exists;
  - observed topics for `solves` task mapping.
- Notes:
  - `updated_at` is treated as repository update metadata, not publication time for news/jobs.
  - GitHub rate-limit headers are captured in source feasibility output.

#### PyPI JSON API

- Access: `https://pypi.org/pypi/{package}/json`.
- Configured packages:
  - `openai`
  - `anthropic`
  - `groq`
  - `mistralai`
- Used for: AI SDK/tool records and conservative company/author observations.
- Supplies:
  - package name;
  - summary;
  - version;
  - Python requirement;
  - license when supplied;
  - project URLs;
  - author / author-email fields.
- Relationship evidence:
  - `Company → develops → Tool` from PyPI author metadata.
- Notes:
  - PyPI package metadata is not treated as a broad product catalog.
  - package update/version metadata is not treated as product launch time.

#### NPM Registry MCP Packages

- Access: NPM package JSON documents.
- Configured packages:
  - `@modelcontextprotocol/server-filesystem`
  - `@modelcontextprotocol/server-memory`
  - `@modelcontextprotocol/server-sequential-thinking`
  - `@modelcontextprotocol/server-github`
- Used for: MCP records and MCP/tool task relationships.
- Supplies:
  - package name;
  - package description;
  - latest version;
  - bin field;
  - deprecation notice when present;
  - README evidence for npm/npx installation wording.
- Relationship evidence:
  - `MCP → integrates_with → Tool` for the GitHub MCP package from the NPM package description naming the GitHub API.
  - `MCP → solves → Task` from controlled mappings over observed package descriptions.

#### NPM Search AI Tool Packages

- Access: NPM registry search endpoint plus package-specific registry documents.
- Configured bounded queries include:
  - `keywords:openai`
  - `keywords:llm`
  - `keywords:ai-sdk`
  - `keywords:stable-diffusion`
  - `keywords:model-context-protocol`
- Used for: additional source-backed package/tool records, with MCP and Creative categories only when observed package name/description evidence supports them.
- Supplies:
  - package name;
  - package description;
  - NPM package URL;
  - latest version;
  - license when present;
  - keywords;
  - package version timestamp;
  - download counts from NPM search.
- Notes:
  - NPM packages are not treated as products.
  - package dates are version/update timestamps, not launch/news publication timestamps.
  - package publisher/maintainer fields are not treated as company identity.
  - each accepted search hit is verified against its package-specific registry document before export.
  - AI relevance filtering uses token/phrase matching for short terms such as `ai`, `llm`, `gpt`, and `mcp` so unrelated substrings inside longer words are not accepted as evidence.
  - A generic keyword-only signal such as only `ai`, `llm`, `gpt`, or `agent` is not enough for acceptance; keyword-only acceptance requires multiple explicit signals with at least one stronger source-specific signal.
  - Creative category assignment is not made from keyword-only metadata or broad README image/badge mentions; it requires package name or package description evidence.
  - Accepted NPM search package metadata includes the field/signals/excerpt used as AI relevance evidence, and Creative records include category evidence.

#### AI Tools List Product Directory

- Access: GitHub REST contents API for `lakey009/AI-Tools-List` sample JSON.
- Used for: bounded Product records, not package/SDK/repository/model records.
- Latest verified inventory: `1001` sample rows; `836` candidate rows after required-field, AI-evidence, and product-semantics filtering.
- Current bounded ingestion limit: `50`.
- Supplies source-backed product fields:
  - directory ID;
  - handle;
  - website/canonical URL;
  - description.
- Does **not** supply reliable provider/company identity, launch date, or publication freshness. Those remain `null` or absent.
- Notes:
  - accepted rows require handle, website, description, valid URL, explicit AI evidence in the product description, and product/service/platform semantics;
  - guide/article/tutorial/course/newsletter blurbs and model-family/company descriptions are rejected even if they mention AI;
  - root `www` URL variants are deduplicated during Product discovery;
  - records include `product.ai_relevance_evidence` with source field/signals/excerpt;
  - the full JSON file exists but is too large for GitHub contents base64; `raw.githubusercontent.com` failed from this environment, so the implemented adapter intentionally uses the reachable sample JSON file.

#### Official SDK Model Definitions

- Access: GitHub REST contents API for official provider SDK type files.
- Sources:
  - `openai/openai-python` generated `ChatModel` type file;
  - `anthropics/anthropic-sdk-python` generated `Model` type file.
- Used for: model records and `Company → develops → Model` relationships.
- Supplies:
  - model identifier literals;
  - provider identity from official SDK repository configuration;
  - source file path and line number.
- Does **not** supply:
  - model license;
  - modalities;
  - pricing;
  - launch/publication timestamp.
- Those fields remain `null` unless a source provides them.

#### Models.dev GitHub Model Catalog

- Access: GitHub REST contents API for `anomalyco/models.dev` generated `models.json`.
- Used for: bounded Model metadata records from providers not already covered by the official OpenAI/Anthropic SDK model adapter.
- Latest verified inventory: `364` model rows; `255` candidate rows after required fields, alias/free-variant filtering, and OpenAI/Anthropic duplicate-avoidance.
- Current bounded ingestion limit: `12`.
- Supplies source-backed model fields:
  - model ID;
  - name;
  - description;
  - provider identity from source ID/name;
  - modality string;
  - input/output modalities;
  - context length and max completion tokens when supplied;
  - supported parameters;
  - knowledge cutoff/source `created` fields when supplied.
- Does **not** supply per-model license. License remains `null`.
- The source `created` field is preserved as source metadata but is **not** treated as an independently verified model release date.
- Direct `https://models.dev/api.json` probing still fails in this environment; this adapter uses the reachable GitHub source path for the same open-source catalog.

#### ROS Robots Catalog

- Access: GitHub REST contents API for `ros-infrastructure/robots.ros.org` Jekyll `_posts` Markdown records.
- Used for: bounded Robot records, not robotics software repositories.
- Latest verified inventory: `208` post files listed; `30` sampled; `29` sampled usable Robot records after semantic filtering.
- Current bounded ingestion limit: `15`.
- Supplies source-backed robot fields:
  - title/name;
  - catalog post date;
  - introduction/description/body text;
  - robot class such as ground/aerial/marine/component;
  - tags;
  - website and/or ROS wiki homepage where supplied;
  - source catalog post URL.
- Does **not** supply a dedicated manufacturer/provider field. Those remain `null`.
- The front-matter date is preserved as `robot.catalog_posted_at`; it is the catalog post date and is **not** treated as a robot launch date.
- The adapter rejects observed software-support blurbs such as ROS-Industrial repository/support records even when they appear in the catalog.

### Feasibility probes without accepted records

The pipeline also records feasibility probes for candidate sources before implementing adapters. Current findings are in:

- `data/source_feasibility.json`
- `docs/source_feasibility.md`

Current probes include:

- Hugging Face Hub API : models, currently unusable in this environment due TLS/network failure.
- OpenAI News RSS : news, currently unusable in this environment due TLS/network failure.
- Y Combinator Companies AI page : startups/companies, currently unusable due TLS/network failure before HTML inspection.
- Product Hunt GraphQL : products, currently unusable due TLS/network failure before schema/auth inspection.
- Hacker News Algolia AI Stories : news/story candidate, currently unusable due TLS/network failure before JSON field inspection; even if reachable, external article publication time would still need validation.
- Himalayas AI Jobs API : jobs candidate, currently unusable due TLS/network failure before posting timestamp inspection.
- GDELT AI News API : news candidate, currently unusable due TLS/network failure; GDELT seendate is not assumed to be publisher publication time.
- Models.dev Model Metadata API : model-enrichment candidate, currently unusable due TLS/network failure before modalities/license inspection.
- NPM Search AI Packages : products/tools, currently `partial`; reachable, but package search results are not automatically product records.
- OpenRouter Models API : models, currently unusable due TLS/network failure.
- TechCrunch AI RSS : news, currently unusable due TLS/network failure.
- VentureBeat AI RSS : news, currently unusable due TLS/network failure.
- Remotive AI Jobs API : jobs, currently unusable due TLS/network failure.
- RemoteOK Jobs API : jobs, currently unusable due TLS/network failure.

No source is marked usable without observed evidence.

## Entity schema

Every accepted entity exports the required common fields:

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

The pipeline also exports:

- `metadata` for domain-specific values;
- `provenance` with source record ID, source URL, observed fields, transformation history, and fetch timestamp when available.

Implemented metadata support includes:

- repositories:
  - stars;
  - primary language;
  - last updated timestamp;
- MCP:
  - installation method;
  - runtime requirements when supplied;
  - package name/version/bin/deprecation fields;
- companies:
  - founding year;
  - industry sector;
  - headquarters;
  - these remain `null` unless source evidence supplies them;
- models:
  - license when supplied;
  - modalities;
  - input/output modalities;
  - provider;
  - context/capability fields when supplied;
  - current model records all have provider evidence; `12` Models.dev records have source-supplied modalities/input/output metadata; license remains `null` because no verified source supplies per-model license;
- products:
  - directory ID/handle;
  - canonical URL;
  - provider when supplied;
  - AI relevance evidence;
  - current product records have directory identity/URL/description evidence, while provider remains `null` because the source does not reliably supply it;
- robots:
  - catalog slug/URL;
  - robot class;
  - tags;
  - website/wiki homepage when supplied;
  - catalog post date;
  - identity evidence;
  - manufacturer/provider remain `null` because the ROS Robots source does not expose dedicated manufacturer/provider fields.

## Entity resolution and mapping log

Entity resolution is deterministic and auditable.

Implemented rules include:

- URL normalization for identity comparisons;
- GitHub path case normalization;
- preservation of GitHub source-code line anchors when they are used as evidence locators;
- normalized company/task names;
- organization suffix removal for common company forms;
- tested alias handling for `OpenAI`, `Open AI`, and `OpenAI, Inc.`;
- canonical URL identity for URL-addressable entities;
- normalized-name identity for companies and tasks;
- stable UUIDv5 IDs from canonical keys;
- duplicate candidate merging;
- mapping log generation.

Mapping decisions are written to `data/entity_mapping_log.json` with:

- raw value;
- canonical value;
- method;
- confidence;
- source URL;
- raw source key;
- canonical ID;
- reason.

## Duplicate/shared URL warning investigation

The previous validation report contained five duplicate normalized URL warnings. They were investigated.

Findings:

1. `f/prompts.chat` duplicate:
   - Cause: two task entities used the repository API URL as their entity URL.
   - Fix: GitHub-topic-derived task entities now use canonical GitHub topic URLs such as `https://github.com/topics/llm` where the raw observed value is a GitHub topic.
   - Result: this duplicate warning is removed.

2. Four NPM MCP package duplicates:
   - URLs:
     - `https://registry.npmjs.org/@modelcontextprotocol%2Fserver-filesystem`
     - `https://registry.npmjs.org/@modelcontextprotocol%2Fserver-memory`
     - `https://registry.npmjs.org/@modelcontextprotocol%2Fserver-sequential-thinking`
     - `https://registry.npmjs.org/@modelcontextprotocol%2Fserver-github`
   - Cause: each MCP package and the task entity derived from its description share the package source URL.
   - Interpretation: the MCP package and task label are distinct entities; the task URL is explicitly marked in metadata as `url_role=evidence_source_url` because no canonical external task URL was observed from that source.
   - Fix: validation warnings now include grouped entity details and classify these as `shared_evidence_url` instead of a generic duplicate URL.
   - Result: warnings are retained and documented rather than suppressed.

This preserves provenance while making the entity URL/source URL distinction explicit.

## Relationship graph

Output file: `data/relationships.json`.

Currently produced relationship types:

- `develops`
- `solves`
- `integrates_with`

Supported relationship types in validation:

- `develops`
- `solves`
- `integrates_with`
- `runs`
- `published_by`
- `hosts`

Current evidence-backed relationships include:

- `Company → develops → Tool` from PyPI author metadata;
- `Company → develops → Model` from official SDK model literal evidence;
- `Repository/Tool/MCP → solves → Task` from observed GitHub topics or package description phrases;
- `MCP → integrates_with → Tool` from the NPM package description for `@modelcontextprotocol/server-github`.

Relationships are not created from guesses. Every relationship has:

- source entity ID;
- target entity ID;
- relationship type;
- evidence object;
- source URL;
- method;
- confidence.

## Validation

`data/validation_report.json` includes:

- total discovered/extracted/cleaned/normalized/deduplicated/classified;
- total relationships;
- total valid/rejected;
- per-source counts;
- per-category counts;
- per-entity-type counts;
- provenance coverage;
- failure counts by type;
- detailed warnings;
- source failures;
- embedded source-feasibility observations.

Validation checks include:

- required entity fields;
- schema validity;
- supported entity types;
- supported categories;
- valid URLs;
- provenance presence;
- duplicate IDs;
- duplicate/shared URLs as warnings;
- repository metadata shape;
- MCP metadata presence;
- model metadata presence/provider support;
- relationship schema;
- relationship endpoints;
- relationship provenance/evidence.

## Retry and failure strategy

The AI Orbit HTTP client in `src/ai_orbit/utils/http.py` distinguishes:

- HTTP `429` rate limiting;
- HTTP `413` payload too large;
- HTTP `404` not found;
- HTTP `403` forbidden;
- timeout;
- network failure;
- malformed JSON;
- generic HTTP error.

Retries are bounded and use exponential backoff with jitter. A source failure is recorded and isolated; records from other sources continue through validation.

## LLM usage

The AI Orbit JSON pipeline currently does not use LLMs for factual extraction because the accepted sources are structured APIs or source files.

The repository still contains an existing provider-agnostic LLM orchestration layer in `src/llm/`. It is separate from the AI Orbit structured-source run. The prior live fallback path should be understood narrowly: Gemini returned 429, Cohere fallback extraction ran, Groq adjudication ran, and deterministic validation accepted that test result. The full normal Gemini → Cohere → Groq path is not claimed as live-proven here.

## How to run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Optional. The small AI Orbit slice runs without secrets.
cp .env.example .env

.venv/bin/python run.py
```

Outputs are written to `data/`.

## How to test

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```

Current verified result:

```text
85 passed
```

AI Orbit-specific tests cover:

- entity normalization;
- OpenAI/Open AI/OpenAI, Inc. resolution;
- URL normalization;
- GitHub line-anchor preservation for source evidence;
- deduplication;
- provenance validation;
- relationship endpoint validation;
- schema/business validation;
- bounded retry behavior;
- source failure isolation;
- official SDK model literal parsing;
- NPM search/package filtering, substring false-positive rejection, weak keyword-only rejection, and MCP/Creative classification;
- NPM MCP `New/Recently Added` category evidence from source publication timestamps rather than version-string shape;
- task mapping guardrails for derived integration-target tools and overly broad filesystem wording;
- Product entity validation, AI Tools List product-directory filtering, Product semantic rejects, and Product URL deduplication;
- Models.dev catalog filtering and model metadata preservation;
- ROS Robots catalog parsing, Robot metadata validation, and software-support record rejection.

## Generated artifacts

Required artifacts:

- `data/entities.json`
- `data/relationships.json`
- `data/entity_mapping_log.json`
- `data/validation_report.json`

Additional artifacts:

- `data/source_feasibility.json`
- `data/categories/*.json`
- `docs/source_feasibility.md`

Category exports are derived from `data/entities.json` and are convenience outputs, not independent sources of truth.

## Configuration

AI Orbit environment variables are listed in `.env.example`.

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
- `AI_ORBIT_OFFICIAL_SDK_MODEL_LIMIT_PER_PROVIDER`
- `AI_ORBIT_NPM_SEARCH_TOOL_LIMIT_PER_QUERY`
- `AI_ORBIT_NPM_SEARCH_TOOL_MAX_RECORDS`
- `AI_ORBIT_AI_TOOLS_PRODUCT_DIRECTORY_API_URL`
- `AI_ORBIT_AI_TOOLS_PRODUCT_LIMIT`
- `AI_ORBIT_MODELS_DEV_GITHUB_CATALOG_API_URL`
- `AI_ORBIT_MODELS_DEV_MODEL_LIMIT`
- `AI_ORBIT_ROS_ROBOTS_CATALOG_API_URL`
- `AI_ORBIT_ROS_ROBOTS_LIMIT`
- `GITHUB_TOKEN` optional for higher GitHub API rate limits

No real credentials are committed.

## Implemented now

- Modular AI Orbit pipeline.
- Real source verification.
- Source-backed ingestion from GitHub API, PyPI JSON API, NPM registry MCP package documents, NPM search/package documents, official SDK model definitions, the AI Tools List product directory sample, the Models.dev GitHub model catalog, and the ROS Robots Catalog.
- Feasibility-only probes for startup/company, product, model, model-enrichment, news/story, and job candidates.
- Stable UUID generation.
- URL normalization and GitHub evidence line-anchor handling.
- Deterministic entity normalization and deduplication.
- Entity mapping log.
- Controlled task classification from observed source metadata, with guardrails for derived integration targets and over-broad wording.
- Evidence-backed relationship extraction, including company/model relationships.
- Validation report with metrics, failures, warnings, and source feasibility.
- Required JSON storage artifacts.
- Automated tests for core behavior.

## Planned / future work

- Expand from `148` current valid entities toward the requested 250–300 high-quality representative records.
- Keep NPM search records classified as package/tool records, not products; expand Product coverage only through sources that directly provide product identity fields.
- Continue model metadata enrichment. The Models.dev GitHub catalog now supplies modalities for a bounded sample, but no verified source currently supplies per-model license fields.
- Find reachable news feeds/APIs with publication timestamps; current tested news/story candidates failed in this environment or do not yet establish external article publication time.
- Find reachable jobs APIs with posted timestamps; current tested jobs candidates failed in this environment.
- Add broader products/devices/video/personal sources only after source feasibility is verified and the source establishes entity identity directly.
- Add `Device → runs → Model` relationships only from direct source evidence.
- Improve assessment-scale cross-source entity resolution as more source families are added.

## Known limitations

- This is not yet the final 250–300 record dataset.
- Several candidate sources fail in this environment at TLS/network setup and are recorded as unusable.
- Model license is not populated; the official SDK model source does not supply modalities, while the Models.dev GitHub catalog supplies modalities for its bounded records only.
- Current jobs/news/video/device/personal categories have no accepted records because tested sources were not reachable or did not yet prove required identity/timestamp semantics, and no fallback data was fabricated.
- Product coverage is currently limited to a bounded directory sample; provider/company and launch-time metadata remain unavailable from that source. Packages, SDKs, repositories, models, features, and tasks are not reclassified as products without direct product-source evidence.
- Robot coverage is currently limited to a bounded ROS Robots catalog sample; manufacturer/provider are not populated because the source does not expose dedicated fields.
- Four shared URL warnings remain intentionally for task labels derived from NPM package descriptions where the source URL is the only observed URL for the task evidence.
- Google Sheets remains part of the older research-paper export path; it is not the AI Orbit system of record.
