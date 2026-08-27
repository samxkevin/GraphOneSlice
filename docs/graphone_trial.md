# GraphOne trial — separate source-of-truth output

> **Scope boundary:** GraphOne counts are not AI Orbit counts. The AI Orbit
> corpus is a representative entity graph, while the GraphOne trial has its own
> tab-oriented source-of-truth artifacts under [`data/graphone/`](../data/graphone/).

## Final local build

The final build was executed at `2026-08-27T12:07:08+00:00`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.graphone.build
```

`data/graphone/validation_report.json` reports `status: passed`, zero validation
failures, 100% provenance coverage, and 100% mapping coverage. Its measured
accepted rows are:

| Required tab | Accepted rows | Source / quality boundary |
| --- | ---: | --- |
| Startups | 1,000 | Public YC Vault `YC_Companies.csv` snapshot, pinned to the source commit and blob. Active rows require a direct positive `Team Size` observation. |
| Products | 1,000 | AI Tools List full directory, pinned to the source commit and blob. Product handle, URL, description, explicit AI evidence, and product semantics are required. |
| Research Papers | 1,000 | Existing arXiv output preserved and independently revalidated; no new arXiv crawl was performed. |
| Jobs | 0 | No source proved an actual employer `posted_at` timestamp. No crawl/listing-added/update timestamp was substituted. |
| News | 10 | GitHub release announcements with source `published_at` within `2026-08-26T12:07:08+00:00` through `2026-08-27T12:07:08+00:00`. |
| Entity Mapping Log | 3,010 | One deterministic mapping record for every accepted startup, product, research-paper, and News record. |

The final 24-hour requirement applies to **News and Jobs only**. The dated
startup and research-paper source snapshots are explicitly labeled as such.

## Artifacts

- [`startups.json`](../data/graphone/startups.json)
- [`products.json`](../data/graphone/products.json)
- [`research_papers.json`](../data/graphone/research_papers.json)
- [`jobs.json`](../data/graphone/jobs.json)
- [`news.json`](../data/graphone/news.json)
- [`entity_mapping_log.json`](../data/graphone/entity_mapping_log.json)
- [`rejected_records.json`](../data/graphone/rejected_records.json)
- [`validation_report.json`](../data/graphone/validation_report.json)
- [`run_manifest.json`](../data/graphone/run_manifest.json)
- [`sheets/`](../data/graphone/sheets/) — six CSVs named exactly for the target
  Google Sheets tabs.

Each output record retains `source_url`, `source_record_id`, `collectedAt`, and
record-level `provenance`. Startup source rows are intentionally not joined by
position to the source repository's separate `YC_URLs.csv`: it has no company
name key, so that would be an unsupported inference. The startup `source_url`
points to the pinned company snapshot and source row instead.

## Startup source and resolution policy

The source is a public, dated YC Directory snapshot from
[`lukaflpvc/YC-Vault`](https://github.com/lukaflpvc/YC-Vault/blob/1c86f32a981d479249496298f6bb746ff3c79efe/README.md).
The repository describes `YC_Companies.csv` as company profiles and metrics from
its YC directory database. The exact input is immutable at:

- [source file](https://github.com/lukaflpvc/YC-Vault/blob/1c86f32a981d479249496298f6bb746ff3c79efe/data/2025-04-21/YC_Companies.csv)
- [source blob API](https://api.github.com/repos/lukaflpvc/YC-Vault/git/blobs/cda06c1570edf61b4e2200b5cc1de53fed4376ad)

The source includes homonyms such as distinct companies named “Apollo” in
different batches. Because it offers no stable cross-row company identifier,
name-only deduplication would falsely merge distinct startups. The pipeline
therefore uses deterministic `source_row_identity` IDs and logs that decision.
`Team Size` is treated as the source snapshot's employee-count observation, not
as a current re-verification.

## Product source and quality policy

The source is the full public
[`AIToolsList.json`](https://github.com/lakey009/AI-Tools-List/blob/ccdff902d7e77774df46e66761e811ada4838ea1/AIToolsList.json)
from `lakey009/AI-Tools-List`, accessed through the pinned
[Git blob API](https://api.github.com/repos/lakey009/AI-Tools-List/git/blobs/208576ae39b4cf1f4a96e448378b7582dc679559).

Of 19,466 source rows, the final run found 15,770 distinct candidate product
URLs after rejecting 3,264 rows without explicit AI evidence, 227 editorial or
non-product semantic rows, and 205 duplicate canonical URLs. The first 1,000
valid candidates in source order make the target export. The directory has no
reliable provider/company or pricing-model field; both are explicitly `null` in
every GraphOne product output rather than inferred from branding or a package.

## News and Jobs freshness policy

`News` accepts a GitHub release only when all of the following are source-backed:

1. non-draft and non-prerelease release identity;
2. title, canonical release URL, publisher, and direct release API URL;
3. `published_at` supplied by GitHub for the release;
4. timestamp inside the exact final 24-hour interval;
5. observed AI relevance in the repository description, topics, or full name.

A repository `updated_at`, release `created_at`, crawling time, and Git commit
time are never used as publication time.

`Jobs` accepts nothing without an actual employer posting timestamp. The
SimplifyJobs source was reachable, but its documentation defines `date_posted`
as the time a listing was added to its own list; it was rejected. The Greenhouse
and Lever candidate endpoint probes failed with TLS connection errors in this
execution environment. Their probe times were not converted into job timestamps.
The exact checks and errors are preserved in `jobs.json`, `rejected_records.json`,
and the validation report.

## Google Sheets export

CSV files are the export payload; JSON artifacts remain the source of truth.
`run_graphone.py --sync-sheets` creates/replaces the six exact target tabs only
when `data/graphone/validation_report.json` is `passed`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_graphone.py --skip-build --sync-sheets
```

The command needs a non-committed service account path and spreadsheet ID via
`GOOGLE_SERVICE_ACCOUNT_JSON_PATH` and `GOOGLE_SHEETS_SPREADSHEET_ID`. This
checkout had neither setting nor a service-account key, so it **did not claim a
GraphOne Sheet synchronization**. The previously linked public Sheet remains
an independently viewable research-paper Sheet; it must not be represented as
having the six GraphOne tabs until the authenticated command succeeds.
