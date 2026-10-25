# GhostTrace Final Run: Model Usage and Cost

This baseline operates entirely on local participant-provided evidence using Python standard-library parsers and deterministic policy logic. It makes **zero** model API calls.

| Provider | Model | Calls | Input tokens | Output tokens | Total tokens | Cost |
|---|---|---:|---:|---:|---:|---:|
| Google Gemini | gemini-3.7-flash (not invoked) | 0 | 0 | 0 | 0 | $0.00 |
| Cohere | command-a-plus-05-2026 (not invoked) | 0 | 0 | 0 | 0 | $0.00 |
| Groq | openai/gpt-oss-120b (not invoked) | 0 | 0 | 0 | 0 | $0.00 |
| **Overall actual usage** | **None** | **0** | **0** | **0** | **0** | **$0.00** |

Total model calls: 0. Input tokens: 0. Output tokens: 0. Total tokens: 0. Mean tokens per evaluation request: 0. Estimated model cost: $0.00 total and $0.00 per request.

This is actual architecture-level usage, not a provider billing measurement. It excludes GitHub Actions compute, network bandwidth, time spent developing, and hardware electricity. The original GraphOneSlice Gemini/Cohere/Groq extraction chain was inspected but **not invoked** in the measured execution. GhostTrace has an optional three-provider quote-validated intent adapter in code/ai_bridge.py, which is disabled by default. Offline mocked provider tests do not count as real model calls.

If a future revision enables model calls, this report must be regenerated using real provider usage records.
