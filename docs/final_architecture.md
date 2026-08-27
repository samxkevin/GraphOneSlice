# Final architecture and evidence boundaries

`GraphOneSliceSystemArchitecture.pdf` remains the original architecture
artifact. This document records the final two-workstream architecture added for
the final submission.

```text
AI ORBIT (representative entity graph)
  Source adapters
    -> discovery / extraction
    -> cleaning
    -> normalization
    -> deterministic entity resolution and deduplication
    -> category classification and task creation
    -> evidence-backed relationship mapping
    -> validation
    -> committed JSON artifacts under data/

GRAPHONE TRIAL (separate tab-oriented dataset)
  Pinned public startup/product source snapshots + preserved research CSV
  + GitHub Releases API for fresh News
    -> source-specific quality gates
    -> deterministic IDs / conservative mapping records
    -> GraphOne tab validation
    -> committed JSON + six CSV export artifacts under data/graphone/
    -> optional Google Sheets clear-and-rewrite synchronization

REVIEWER
  reviewer_app.py (local, read-only HTTP server)
  + reviewer_site/ (static route bundle)
    -> only reads committed artifact files
    -> never calls ingestion adapters or external sources
    -> ready-to-enable GitHub Pages workflow template packages reviewer_site + data/ from main
```

## Isolation guarantees

| Boundary | Guarantee |
| --- | --- |
| AI Orbit vs. GraphOne | AI Orbit's 254 entities/134 relationships are not used to satisfy GraphOne's 1,000 startup/product/research-paper targets. |
| Source vs. artifact | Every accepted record stores a source URL and provenance. Pinned Git commit/blob URLs make the startup/product inputs independently retrievable. |
| Freshness vs. collection time | News uses GitHub Release `published_at`; Jobs require employer `posted_at`. Retrieval, update, commit, and listing-added times are rejected as substitutes. |
| Missing facts | Product provider/pricing and unavailable source metadata are represented as `null`; neither LLM output nor naming heuristics is used to fill them. |
| Source outage vs. corpus preservation | GraphOne retrieves required remote sources and validates in memory before replacing any output artifact. A mandatory source collapse raises before writes. |
| Reviewer vs. pipeline | The reviewer serves static committed JSON/CSV and has no ingestion imports or network requests. |
| Sheets vs. source of truth | The Sheets exporter only copies already validated CSVs. It refuses to sync when validation fails and never treats a Sheet as an input. |

## Data contracts

### AI Orbit

- `data/entities.json`
- `data/relationships.json`
- `data/entity_mapping_log.json`
- `data/validation_report.json`
- `data/source_feasibility.json`
- `data/categories/*.json`

### GraphOne

- `data/graphone/startups.json`
- `data/graphone/products.json`
- `data/graphone/research_papers.json`
- `data/graphone/jobs.json`
- `data/graphone/news.json`
- `data/graphone/entity_mapping_log.json`
- `data/graphone/rejected_records.json`
- `data/graphone/validation_report.json`
- `data/graphone/run_manifest.json`
- `data/graphone/sheets/{Startups,Products,Research Papers,Jobs,News,Entity Mapping Log}.csv`

The reviewer routes `/`, `/ai-orbit`, `/graphone`, `/entities`, `/relationships`,
`/validation`, `/mapping`, `/feasibility`, and `/categories` surface these exact
committed artifacts.
