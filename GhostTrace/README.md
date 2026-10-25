# GhostTrace — Evidence-Grounded Data Deletion Audit Agent

Submission implementation for **HackerRank Orchestrate October 2026: Ghost Data Still Exists**.

**Important:** This project lives in \`GraphOneSlice/GhostTrace/\` on the isolated branch \`ghosttrace-orchestrate-oct2026\`. The original GraphOneSlice application remains unchanged; \`GhostTrace/\` is the challenge project root.

## Run

Requires Python 3.11 or newer. Standard-library pipeline: no API key needed.

\`\`\`bash
git clone --branch ghosttrace-orchestrate-oct2026 https://github.com/samxkevin/GraphOneSlice.git
cd GraphOneSlice/GhostTrace
git clone --depth 1 https://github.com/interviewstreet/hackerrank-orchestrate-october26.git official
cp -r official/dataset ./dataset
python code/main.py --sample
python code/evaluation/evaluate.py --dataset dataset --pred sample_predictions.csv --output code/evaluation/evaluation_report.md
python -m unittest discover -s code/tests -v
python code/main.py
\`\`\`

The output file is \`GhostTrace/output.csv\` (root of this challenge implementation). It has exactly \`case_id,deletion_status,steps_json\`, sorted by case ID.

Do **not** submit the official dataset, private keys, \`.env\`, caches, or \`official/\`. The code ZIP is built with:

\`\`\`bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*.pyc" "*.zip"
\`\`\`

All three submission artifacts are \`code.zip\`, \`output.csv\`, and \`log.txt\` (the actual coding-agent conversation transcript, if available).

## Architecture

\`\`\`
deletion_requests.csv -> multilingual intent detection
                     -> current+historical identifier graph
                     -> manifest-authorized source processing:
                        JSON, SQL, logs, handovers, PDF text
                     -> provenance-preserving resource facts
                     -> audit_at filter -> resource state reconstruction
                     -> policy treatment & recreation risk
                     -> ordered findings / remediation / verification
                     -> strict CSV & JSON contract checks
\`\`\`

The current inference path is deterministic Python. The \`code/evidence_base.py\` extractor is the runnable fallback; a richer \`code/evidence.py\` can be added without changing \`code/main.py\`. Input data is read from \`dataset/\` only, not organizer-only truth. Each sourced fact includes an evidence ID and observation timestamp.

### Reused GraphOneSlice patterns and model decision

The original GraphOneSlice factual-extraction path is:
- **Google Gemini \`gemini-3.7-flash\`**: initial structured extraction of directly supported facts and quotes.
- **Cohere \`command-a-plus-05-2026\`**: evidence-based review/correction; extraction fallback.
- **Groq-hosted \`openai/gpt-oss-120b\`**: final adjudication of extracted claims.
- Deterministic validation rejects supported claims without exact source substrings.

The challenge implementation adapts the *patterns*: evidence-first extraction, structured facts, provenance, failure isolation and deterministic validation. It does **not** claim to have copied or invoked GraphOneSlice's job-field-specific multi-model chain. There is currently no installed live provider credential; the measured evaluation and usage report reflect the actual deterministic run.

Model calls are not necessary to calculate state from structured SQL/JSON/log records. Multimodal scanned/image evidence remains a quality gap until a source-validated parser is integrated. Do not claim production-grade PDF/image extraction from this baseline.

## Policy safeguards

- Reported workflow \`COMPLETE\` is never used as proof of deletion.
- A request that does not authorize deletion gets \`NOT_APPLICABLE\`, \`[]\`.
- Stable user IDs, previous emails and email hashes are joined only through user snapshot and change audit.
- Evidence timestamps are compared with \`audit_at\`; records after the cutoff must not change earlier outcomes.
- \`RETAIN\` records remain; tombstones redact direct identifiers but may preserve stable references.
- Incomplete cases place supported findings before proposed fixes and verification. Proposed steps cite empty evidence IDs.
- Deletion-risk decisions should be based on all relevant system copies, including replicas, backups and active sync.
- Missing evidence is **not** interpreted as proven deletion. A no-evidence case is conservatively treated as incomplete rather than fabricated complete.

## Tests and evaluation

\`code/tests/test_core.py\` includes separate tests for: non-deletion requests, false COMPLETE dashboards, historical identifiers, active restore paths, post-audit evidence, mandatory retention, and multilingual intent.

\`code/evaluation/evaluate.py\` reports **measured** case-level status accuracy, exact sequence matching, exact field-level alignment, step precision and recall against the **32 authorized labelled sample outputs**. It validates all 518 generated rows against the exact output contract, without access to hidden canonical answers.

\`code/evaluation/evaluation_report.md\` is generated by a real run. It contains actual measured metrics and failures. \`code/evaluation/usage_report.md\` states actual usage and does not invent model-token counts.

Automated CI workflow: \`.github/workflows/ghosttrace.yml\` on this branch checks out participant-facing data, runs tests, generates samples, evaluates, produces 518 predictions, validates their schema, builds \`code.zip\`, and publishes artifact files to this branch.

## Known limitations

The model-neutral fallback parser handles structured text but cannot reliably interpret screenshot contents; PDF extraction requires the \`pdftotext\` executable. Some account absence and anonymization proofs lack a direct subject reference, producing lower recall. No hidden-label evaluation accuracy can be reported. The submission is a best-effort evidence audit, not a claim that every data source was successfully read.
