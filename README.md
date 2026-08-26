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

- valid entities: `252`
- valid relationships: `135`
- validation status: `passed`
- validation failures: `0`
- rejected records: `0`
- provenance coverage: `100%`
- recorded source failures: `15`
- duplicate/shared URL warnings: `4`
- test result: `133 passed`
- relationship types produced: `develops` (20), `solves` (27), `published_by` (10), `integrates_with` (1), `runs` (77)

This is still an assessment vertical slice / early expansion, not the final 250–300 record representative corpus.

## Verification status labels

- **LIVE VERIFIED**: The current AI Orbit run has live-verified GitHub API, PyPI JSON API, NPM registry MCP package documents, NPM search/package documents, official SDK model definition ingestion, AI Tools List product-directory ingestion, Models.dev GitHub model-catalog ingestion, Qualcomm AI Hub Models catalog ingestion, ROS Robots Catalog ingestion, GitHub Releases announcement (News) ingestion, PyVideo conference-talk (Videos) ingestion, AI device catalog (Devices) ingestion, and Hailo Model Zoo ingestion (Devices + Models + `Device → runs → Model`). The latest executed run produced the counts above.
- **IMPLEMENTED BUT NOT LIVE-VERIFIED**: No additional accepted AI Orbit source adapter is claimed beyond the sources listed as live verified. Candidate probes may be implemented without accepted records.
- **UNIT/MOCK TESTED**: HTTP retry boundaries, source failure isolation, entity normalization/resolution, validation behavior, official SDK literal parsing, NPM relevance filtering, NPM category quality gates, Product quality gates, Models.dev metadata filtering, Qualcomm AI Hub manifest parsing/provider derivation, ROS robot catalog filtering, Hailo model-zoo YAML parsing/compatibility-edge extraction, and task mapping guardrails are covered by automated tests.
- **PLANNED**: Broader product coverage beyond the bounded sample, plus jobs and personal records remain planned until a source proves the required identity and timestamp/metadata fields. News is live-verified via GitHub Releases announcements, Videos via the PyVideo conference-talk catalog, Devices via the AI device catalog and the Hailo model zoo, and `Device → runs → Model` via the Hailo model zoo's explicit `info.supported_hw_arch` declarations; jobs and personal remain blocked — the reachable GitHub-hosted candidates were rejected on timestamp semantics (jobs: `date_posted` = "when added", not employer posting time) and identity (personal: an awesome list of open-source frameworks/tools, not personal-assistant products).
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

#### Qualcomm AI Hub Models

- Access: GitHub REST git-trees API (recursive) + contents API for `qualcomm/ai-hub-models` model `manifest.yaml` files.
- Used for: bounded Model metadata records from Qualcomm's official catalog of models optimized for Qualcomm devices (a distinct vendor from the existing sources).
- Latest verified inventory: `236` model manifests; `34` sampled (deterministic stride) and ingested.
- Supplies source-backed model fields:
  - model ID and display name;
  - description;
  - `license` + `license_type` (34/34 sampled records have a license);
  - `domain` (Computer Vision / Generative AI / Audio / Multimodal), `use_case`, `tags`;
  - `source_repo` (upstream model source), `research_paper` + `research_paper_title`;
  - `technical_details`, `supported_precisions`.
- Provider is the upstream GitHub/Hugging Face owner when the manifest links a source repository (e.g. `ultralytics`, `facebookresearch`, `pytorch`); otherwise the Qualcomm catalog publisher is recorded as provider.
- Does **not** supply per-model release timestamps; none is fabricated. `fetched_at` remains provenance-only.
- Does **not** emit `Device → runs → Model` edges: the per-model manifests declare no explicit supported-device list (the catalog's `devices_and_chipsets.yaml` lists chipsets/devices but supplies no per-chipset canonical URL), so no compatibility edge is inferred.

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

#### GitHub Releases Announcements (News)

- Access: GitHub REST releases API `https://api.github.com/repos/{owner}/{repo}/releases` for a curated allowlist of AI repositories.
- Configured repositories:
  - `huggingface/transformers`
  - `huggingface/diffusers`
  - `huggingface/datasets`
  - `cohere-ai/cohere-python`
  - `groq/groq-python`
  - `mistralai/client-python`
  - `openai/openai-python`
  - `anthropics/anthropic-sdk-python`
  - `modelcontextprotocol/typescript-sdk`
- Used for: bounded `News` records (release announcements), not repository/tool/model records.
- **Semantics — not general news**: these records are **GitHub release announcements**, a distinct News subtype. They are not represented as general press/news articles. Each record carries `news.subtype = "github_release_announcement"` so the distinction is explicit in the data itself.
- Supplies source-backed news fields:
  - title (`name`, falling back to `tag_name`);
  - canonical release URL (`html_url`);
  - publisher (repository owner login/type/html_url);
  - `subtype` (`github_release_announcement`);
  - `published_at` (genuine GitHub release publication timestamp);
  - `created_at`;
  - release-note body (cleaned, bounded excerpt);
  - `tag_name` / `release_id` / `prerelease`;
  - AI relevance evidence from observed repository description/topics/full_name tokens.
- Freshness semantics:
  - `news.published_at` is the time GitHub recorded the release as published; it is **never** substituted with crawl, retrieval, commit, or page-modification time.
  - `news.timestamp_semantics` is set to `github_release_published_at` so the meaning is explicit.
  - `fetched_at` remains a separate provenance field; no `updated_at` is invented for releases.
- Relationship evidence:
  - `News → published_by → Company` is emitted only when the repository owner is a GitHub `Organization` and that organization already resolves to an ingested company entity. OpenAI and Anthropic records carry publisher metadata but no company relationship because their GitHub orgs supply no company description and their company entities are PyPI-sourced.
- Acceptance filters:
  - draft releases and prereleases are rejected;
  - a release must have a valid `html_url`, a parseable `published_at`, a title, and a non-empty release-note body.
- Current bounded ingestion limit: `AI_ORBIT_GITHUB_RELEASES_NEWS_LIMIT=12`, sampled round-robin across repositories so the bounded sample spans as many publishers as possible (newest release per repository first).

#### PyVideo Conference Talks (Videos)

- Access: GitHub REST contents API for the `pyvideo/data` repository (the catalog that powers pyvideo.org), one JSON document per conference-talk video.
- Configured conferences (AI-relevant allowlist):
  - `pycon-us-2025`
  - `pycon-us-2024`
  - `pytorchconf-2024`
  - `pytorchconf-2023`
  - `scipy-2024`
  - `pydata-virginia-2025`
- Used for: bounded `Video` records (actual conference-talk videos), not repositories, packages, or channel listings.
- Supplies source-backed video fields:
  - title;
  - canonical YouTube URL plus extracted `youtube_video_id`;
  - `recorded` (the source-documented date the talk was recorded);
  - description (cleaned, bounded excerpt);
  - publisher (the conference/event the source attributes the talk to);
  - speakers, language, related URLs, thumbnail URL.
- Freshness semantics:
  - `video.recorded_at` is PyVideo's documented **recording date** (`YYYY-MM-DD`) — a recording date, **not** a publication/upload timestamp. The assessment schema does not require a publication timestamp for Videos, so none is fabricated.
  - `video.timestamp_semantics` is set to `pyvideo_recorded_date` so the meaning is explicit.
  - `fetched_at` remains a separate provenance field; no `published_at`/`updated_at` is invented for videos.
- Channel/publisher note: PyVideo does not supply a YouTube channel name. The publisher is recorded as the conference/event (type `conference`); no channel identity is fabricated.
- AI relevance:
  - conference allowlist plus per-record title/description evidence;
  - acceptance requires at least one strong AI signal or at least two weaker AI signals (e.g. `llm`, `machine learning`, `pytorch`, `computer vision` are strong; a lone `ai`, `gpu`, `training`, or `agent` is not enough on its own);
  - matched strong/weak tokens are recorded in `video.ai_relevance_evidence`.
- Acceptance filters:
  - a video must have a title, a canonical YouTube URL, a parseable `recorded` date, a non-empty description, and AI relevance evidence.
- Current bounded ingestion limit: `AI_ORBIT_PYVIDEO_LIMIT=12`, sampled round-robin across conferences so the bounded sample spans as many publishers as possible.

#### AI Device Catalog (Devices)

- Access: GitHub REST contents API for a structured Markdown catalog of embedded boards with AI/ML accelerators (`Vge0rge/ai-ml-embedded-boards`).
- Used for: bounded `Device` records (actual AI-hardware boards), not SDKs, drivers, repositories, or software platforms.
- Supplies source-backed device fields:
  - board name;
  - canonical vendor product URL;
  - MCU/processor description;
  - accelerator evidence (NPU/Ethos/Neural-ART/KPU/PIE tokens observed in the entry);
  - framework support and price where supplied;
  - vendor label.
- Manufacturer semantics:
  - `device.manufacturer` is derived only from the board name via a controlled, source-derived token map (e.g. `NXP MCIMX93-EVK` → NXP, `STM32N6570-DK` → STMicroelectronics); the matched token and observed name are recorded in `device.manufacturer_evidence`;
  - `device.manufacturer` is `null` when the source does not name a manufacturer — it is never guessed.
- Acceptance filters:
  - entries are accepted only from the source's "Available now" and "Boards with other AI/ML Accelerators" sections; "Available later" (announced-only) and "MCUs only" (bare chips, not devices) sections are excluded;
  - a device must have a name, a valid vendor URL, an MCU/processor line, and observed accelerator evidence;
  - two boards sharing one generic catalog URL are deduplicated (the first device-specific occurrence is kept).
- Relationships: **no** `Device → runs → Model` edges are produced, because the source documents framework support (TensorFlow/PyTorch), not specific supported model IDs. Devices carry no speculative relationships.
- Freshness: the source does not supply per-device timestamps, so no release/publication date is fabricated for devices; `fetched_at` remains provenance-only.
- Current bounded ingestion limit: `AI_ORBIT_AI_DEVICE_LIMIT=15`.

#### Hailo Model Zoo (Device → Model compatibility)

- Access: GitHub REST git-trees API (recursive enumeration) plus the contents API for the official `hailo-ai/hailo_model_zoo` repository's `hailo_model_zoo/cfg/networks/*.yaml` files.
- Used for: bounded `Model` records, three `Device` records (Hailo-15H, Hailo-15L, Hailo-10H AI accelerators), and `Device → runs → Model` relationships.
- Why this source: each model YAML declares `network.network_name` (model identity) together with an explicit `info.supported_hw_arch` list naming the Hailo accelerators that run it. This is direct, per-model compatibility evidence — the exact pattern the assessment requires for `Device → runs → Model`, and distinct from framework support or popularity.
- Supplies source-backed fields:
  - model: `network_name`, `supported_hw_arch`, `task`, `input_shape`, `operations`, `parameters`, original `source` URL, `license_name`, and pre-trained artifact `url` where supplied;
  - device: arch code → product name (`hailo15h` → `Hailo-15H`, from the source README's own spelling), per-device docs directory (`docs/public_models/HAILO15H`, `HAILO15L`, `HAILO10H`).
- Evidence rule:
  - a `runs` edge is created **only** when a model's own YAML lists the device in `info.supported_hw_arch`; the edge records `observed_field`, the observed arch list, the model YAML blob URL, and the reason;
  - models whose YAML has no `supported_hw_arch` (six legacy face/person models in the catalog) are excluded — no edge is inferred for them;
  - no edge is inferred from TensorFlow/PyTorch/CUDA generality or from popularity.
- Device identity:
  - `device.manufacturer` = `Hailo` (the repository owner is the official `hailo-ai` organization), recorded with evidence;
  - `device.device_class` = `ai-accelerator`;
  - `device.canonical_url` is the device's own documentation directory in the source (e.g. `docs/public_models/HAILO15H`), not a vendor product page — the manufacturer product pages are on `hailo.ai`, which is unreachable from this environment, so no unverified product URL is fabricated.
- Bounded sample:
  - latest verified catalog inventory: `233` network YAMLs; `227` declare `supported_hw_arch`; `3` device families (Hailo-15H/15L/10H);
  - the adapter ingests a deterministic stride sample (bounded by `AI_ORBIT_HAILO_MODEL_LIMIT=32`) across the alphabetically sorted catalog so the sample spans task families (classification, detection, segmentation, face, NLP, zero-shot) instead of concentrating on one;
  - the latest run ingested `29` sampled models and `3` devices, producing `77` `runs` edges (stride positions hitting legacy no-arch YAMLs are correctly skipped).
- Failure isolation: a single unparseable or no-arch model YAML is skipped without failing the source; tree/contents failures are recorded as source failures.
- Freshness: the source does not supply per-device/per-model publication timestamps, so none is fabricated; `fetched_at` remains provenance-only.

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
- SimplifyJobs Internships Listings : jobs candidate, reachable and parseable (GitHub-hosted `listings.json`; 14,764 listing objects; schema documents `company_name`, `title`, `url`, `locations`, `terms`, `sponsorship`), but `date_posted` is documented as "Unix timestamp when added" (list ingestion time, not the employer's posting time) and the contribution form collects no posting date — rejected for Jobs under the posting-timestamp requirement.
- SimplifyJobs New-Grad Positions : jobs candidate (sibling of the above), reachable with 19,034 listing objects using the same schema; same "when added" `date_posted` semantics, so it is likewise not accepted as a Jobs source.
- Awesome Personal AI Assistants : personal candidate, reachable; a curated Markdown list of open-source self-hosted assistant frameworks/tools (repository links + one-line descriptions), not personal-assistant product identity — rejected under the identity gate.
- GDELT AI News API : news candidate, currently unusable due TLS/network failure; GDELT seendate is not assumed to be publisher publication time.
- Models.dev Model Metadata API : model-enrichment candidate, currently unusable due TLS/network failure before modalities/license inspection.
- NPM Search AI Packages : products/tools, currently `partial`; reachable, but package search results are not automatically product records.
- OpenRouter Models API : models, currently unusable due TLS/network failure.
- TechCrunch AI RSS : news, currently unusable due TLS/network failure.
- VentureBeat AI RSS : news, currently unusable due TLS/network failure.
- Remotive AI Jobs API : jobs, currently unusable due TLS/network failure.
- RemoteOK Jobs API : jobs, currently unusable due TLS/network failure.

Additional one-time reachability probes performed during the News milestone (not added as permanent probes, to avoid repeatedly hitting conclusively-blocked hosts):

- Hacker News Firebase API (`hacker-news.firebaseio.com`) : unusable due TLS/network failure.
- Hacker News Algolia (`hn.algolia.com`) : unusable due TLS/network failure.
- `news.ycombinator.com` : unusable due TLS/network failure.
- Reddit JSON API (`www.reddit.com`, `api.reddit.com`) : unusable due TLS/network failure.
- Lobsters (`lobste.rs`) : unusable due TLS/network failure.
- Wikipedia API (`en.wikipedia.org`) : unusable due TLS/network failure.
- GitHub Blog changelog RSS (`github.blog`) : unusable due TLS/network failure.
- RSSHub (`rsshub.app`) : unusable due TLS/network failure.
- `raw.githubusercontent.com` : unusable due TLS/network failure.
- arXiv API (`export.arxiv.org`) : unusable due TLS/network failure.

Reachability conclusion for this environment: only `api.github.com`, `pypi.org`, and `registry.npmjs.org` returned parseable JSON; every non-GitHub news/feed/jobs/video host probed failed at TLS connection setup with the same error. GitHub REST Releases is therefore the one structured, reachable, GitHub-hosted dataset that supplies genuine publication timestamps for a News category. For Jobs, the reachable GitHub-hosted SimplifyJobs listings were inspected in depth and rejected because their only date field (`date_posted`) means "when added" to the list rather than the employer's posting time; for Personal, the reachable GitHub-hosted candidate was an awesome list of open-source frameworks/tools rather than personal-assistant product records. Neither category gained records, and none were fabricated.

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
  - supported hardware architectures (Hailo model zoo records);
  - task, input shape, operations, parameters, original model source (Hailo model zoo records);
  - current model records all have provider evidence; `12` Models.dev records have source-supplied modalities/input/output metadata; `34` Qualcomm AI Hub records carry source-supplied `license` + `license_url`, `domain`, `use_case`, `source_repo`, and `research_paper`; Hailo model-zoo records carry `supported_hw_arch`/task/shape/ops/parameters and an original `source_repository` where supplied; license remains `null` where no verified source supplies a per-model license;
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
- news:
  - canonical URL;
  - `subtype` (`github_release_announcement` — records are release announcements, not general news articles);
  - `published_at` (source-backed GitHub release publication timestamp);
  - `created_at`;
  - `timestamp_semantics` (`github_release_published_at`);
  - publisher (login/type/html_url);
  - repository;
  - tag name / release id / prerelease;
  - AI relevance evidence (matched fields/tokens/excerpt).
- videos:
  - canonical YouTube URL and `youtube_video_id`;
  - `recorded_at` (source-documented talk recording date);
  - `timestamp_semantics` (`pyvideo_recorded_date`);
  - publisher (conference/event name);
  - speakers, language, related URLs, thumbnail URL;
  - AI relevance evidence (matched strong/weak tokens/excerpt).
- devices:
  - canonical vendor URL;
  - device class (`embedded-ai-board` for the board catalog, `ai-accelerator` for Hailo accelerators);
  - `manufacturer` (source-derived or `null`) plus `manufacturer_evidence`;
  - vendor label and URL;
  - processor/accelerator description, framework support, price;
  - AI relevance evidence (matched accelerator tokens/excerpt).

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
- `published_by`
- `runs`

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
- `MCP → integrates_with → Tool` from the NPM package description for `@modelcontextprotocol/server-github`;
- `News → published_by → Company` from the GitHub release repository owner, emitted only when the owner organization resolves to an ingested company entity.
- `Device → runs → Model` from the Hailo model zoo, emitted only when a model's own YAML declares the device in `info.supported_hw_arch`.

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
- news metadata presence, including a source-backed ISO-8601 `published_at`, explicit `timestamp_semantics`, publisher login, and AI relevance evidence;
- video metadata presence, including a canonical YouTube URL, a source-backed ISO-8601 `recorded_at`, explicit `timestamp_semantics`, a publisher/event name, and AI relevance evidence;
- device metadata presence, including a canonical URL and AI relevance evidence (manufacturer is optional and may be `null`);
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
133 passed
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
- Qualcomm AI Hub manifest parsing, license/provider preservation, and deterministic stride sampling;
- ROS Robots catalog parsing, Robot metadata validation, and software-support record rejection;
- Hailo model-zoo YAML parsing, compatibility-edge extraction, deterministic stride sampling, `Device → runs → Model` direction/evidence, and Hailo device/model validation.

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
- `AI_ORBIT_HAILO_MODEL_ZOO_TREE_URL`
- `AI_ORBIT_HAILO_MODEL_ZOO_CONTENTS_BASE`
- `AI_ORBIT_HAILO_MODEL_LIMIT`
- `GITHUB_TOKEN` optional for higher GitHub API rate limits

No real credentials are committed.

## Implemented now

- Modular AI Orbit pipeline.
- Real source verification.
- Source-backed ingestion from GitHub API, PyPI JSON API, NPM registry MCP package documents, NPM search/package documents, official SDK model definitions, the AI Tools List product directory sample, the Models.dev GitHub model catalog, the Qualcomm AI Hub Models catalog, the ROS Robots Catalog, the AI device catalog, GitHub Releases announcements (News), PyVideo conference talks (Videos), and the Hailo Model Zoo (Devices + Models + `Device → runs → Model`).
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

- Expand from `252` current valid entities toward the requested 250–300 high-quality representative records.
- Keep NPM search records classified as package/tool records, not products; expand Product coverage only through sources that directly provide product identity fields.
- Continue model metadata enrichment. The Models.dev GitHub catalog supplies modalities for a bounded sample, and the Qualcomm AI Hub catalog now supplies per-model license + license URL + domain + use_case + research paper for its 34 sampled records; license remains `null` only where no verified source supplies it.
- Expand News coverage beyond GitHub release announcements only through sources that establish genuine article publication timestamps; external news feed/API candidates remain blocked in this environment.
- Find a Jobs source that supplies a genuine employer `posted_at`/`created_at` timestamp; the reachable SimplifyJobs listings were rejected because `date_posted` means "when added" (list ingestion time), not posting time.
- Add Personal records only from a source that establishes explicit personal-AI-assistant product identity; the reachable awesome list of open-source assistant frameworks/tools does not qualify.
- Broaden `Device → runs → Model` coverage beyond the Hailo bounded sample (e.g. a larger deterministic sample of the 227 compatibility-tagged Hailo models) only if each additional edge remains directly evidenced by the model YAML's `info.supported_hw_arch`.
- Improve assessment-scale cross-source entity resolution as more source families are added.

## Known limitations

- This is not yet the final 250–300 record dataset.
- Several candidate sources fail in this environment at TLS/network setup and are recorded as unusable.
- Model license is only populated where a source supplies it: Hailo model-zoo records carry `license_name` where present, and Qualcomm AI Hub records carry `license` + `license_url` (34/34 sampled records). The official SDK model source does not supply modalities or license, while the Models.dev GitHub catalog supplies modalities (but no license) for its bounded records.
- Current `jobs` and `personal` categories still have no accepted records: the reachable GitHub-hosted jobs candidates (SimplifyJobs internships and new-grad listings) were rejected because `date_posted` means "when added" to the list rather than the employer's posting time, and the reachable personal candidate was an awesome list of open-source assistant frameworks/tools rather than personal-assistant product records. No fallback data was fabricated. (News, Videos, Devices, and `Device → runs → Model` are live-verified.)
- Product coverage is currently limited to a bounded directory sample; provider/company and launch-time metadata remain unavailable from that source. Packages, SDKs, repositories, models, features, and tasks are not reclassified as products without direct product-source evidence.
- Robot coverage is currently limited to a bounded ROS Robots catalog sample; manufacturer/provider are not populated because the source does not expose dedicated fields.
- Hailo device canonical URLs point at each device's documentation directory in the `hailo-ai/hailo_model_zoo` source rather than at a manufacturer product page, because `hailo.ai` is unreachable from this environment and no unverified product URL is fabricated.
- `Device → runs → Model` coverage is limited to a bounded deterministic Hailo model sample (29 models / 77 edges); the full catalog has 227 compatibility-tagged models that could be sampled more broadly later.
- Four shared URL warnings remain intentionally for task labels derived from NPM package descriptions where the source URL is the only observed URL for the task evidence.
- Google Sheets remains part of the older research-paper export path; it is not the AI Orbit system of record.
