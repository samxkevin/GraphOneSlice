# GhostTrace evidence extraction

`code/evidence.py` exports `extract_facts(dataset_dir: pathlib.Path) -> list[dict]`. It reads only entries in `evidence_files.csv`; facts retain the manifest `evidence_id`, `captured_at`, an observation `timestamp`, resource, category, state, source fields, and exact refs. Consumers must require **both** timestamps to be at or before the relevant case cutoff. The extractor does not merge aliases between observations, and identity matching must use exact normalized values / verified joins rather than prefixes or substrings.

JSON records are traversed recursively, including nested exports. SQLite scripts run in a fresh in-memory database per file; every table is inspected independently so primary and replica disagreement remains visible. An SQLite authorizer denies `ATTACH`, `DETACH`, pragmas, and unsafe file/extension functions. Logs and PDF text are parsed as source observations; an operation start or generic task success is not treated as proof of deletion. PDFs require `pdftotext`; missing optional tooling degrades without inventing facts. Image OCR/vision is not currently enabled: image files are skipped and recorded in `GhostTrace/evidence_diagnostics.log` for follow-up validation.

Read and parse failures are logged with manifest ID, path and exception class; source contents and extracted identifiers are deliberately excluded from diagnostics. Unsupported formats and missing manifest files are also reported. Evidence IDs are filtered against IDs declared by the manifest.

## Tests

Run `python -m unittest discover -s GhostTrace/code/tests -p 'test_evidence.py'` from the repository root. The tests cover nested JSON identity refs, independent SQL replicas, similar-identity separation, and external SQL attachment rejection.

## Known limitations

Screenshot/image OCR and text handover-specific parsers are not implemented. PDF text extraction is best-effort via the host `pdftotext` executable. The extractor provides observations, not case-cutoff evaluation or final action recommendations; the caller owns cutoff enforcement and exact identity linkage. Test against the official challenge dataset before relying on sample-case metrics.
