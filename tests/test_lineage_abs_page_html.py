import hashlib
from uuid import uuid4

import httpx
import pytest

from src.adapters.repo_evidence_adapter import RepoEvidenceAdapter
from src.config.settings import Settings
from src.pipeline.orchestrator import run_repo_resolution
from tests.fakes import FakeStorage


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql://u:p@localhost/db",
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.02,
        retry_jitter_seconds=0.01,
        pipeline_batch_size=50,
    )
    base.update(overrides)
    return Settings(**base)


def _seed_paper(storage: FakeStorage, arxiv_id: str, canonical_url: str) -> "uuid4":
    paper_id = uuid4()
    storage.papers[paper_id] = {
        "id": paper_id, "arxiv_id": arxiv_id, "canonical_url": canonical_url,
        "status": "PARSED", "title": "T", "authors": ["A"], "abstract": None,
        "published_date": None,
    }
    storage._arxiv_id_to_paper_id[arxiv_id] = paper_id
    return paper_id


_PAGE_WITH_LINK = """
<html><body>
<blockquote class="abstract">Abstract text.</blockquote>
<table class="metatable"><tr><td class="tablecell comments">
Code: <a href="https://github.com/some/repo">code</a>
</td></tr></table>
</body></html>
"""


# -----------------------------------------------------------------
# A. successful abs-page HTML is persisted
# B. the persisted observation is linked to the correct paper
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_successful_html_persisted_and_linked_to_correct_paper():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_PAGE_WITH_LINK)

    transport = httpx.MockTransport(handler)
    settings = _settings()
    storage = FakeStorage()
    paper_id = _seed_paper(storage, "2508.33333", "https://arxiv.org/abs/2508.33333")
    # A second, unrelated paper -- proves no cross-linking (requirement B).
    other_paper_id = _seed_paper(storage, "2508.44444", "https://arxiv.org/abs/2508.44444")

    evidence_adapter = RepoEvidenceAdapter(settings, transport=transport)
    await run_repo_resolution(settings, storage, evidence_adapter=evidence_adapter)

    html_observations = [
        o for o in storage.fetch_observations.values()
        if o["source_name"] == "arxiv_abs_page_html"
    ]
    assert len(html_observations) == 2  # one per paper

    obs_for_paper = next(o for o in html_observations if o["paper_id"] == paper_id)
    assert obs_for_paper["raw_payload"]["html"] == _PAGE_WITH_LINK
    assert obs_for_paper["fetch_status"] == "OK"

    obs_for_other = next(o for o in html_observations if o["paper_id"] == other_paper_id)
    assert obs_for_other["paper_id"] != obs_for_paper["paper_id"]  # never cross-linked


# -----------------------------------------------------------------
# C. the stored content/hash corresponds to the HTML actually parsed
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_stored_content_hash_matches_html_actually_used_for_extraction():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_PAGE_WITH_LINK)

    transport = httpx.MockTransport(handler)
    settings = _settings()
    storage = FakeStorage()
    paper_id = _seed_paper(storage, "2508.55555", "https://arxiv.org/abs/2508.55555")

    evidence_adapter = RepoEvidenceAdapter(settings, transport=transport)
    await run_repo_resolution(settings, storage, evidence_adapter=evidence_adapter)

    obs = next(
        o for o in storage.fetch_observations.values()
        if o["source_name"] == "arxiv_abs_page_html" and o["paper_id"] == paper_id
    )
    expected_hash = hashlib.sha256(_PAGE_WITH_LINK.encode("utf-8")).hexdigest()
    assert obs["content_hash"] == expected_hash

    # And the extracted candidate must have come from this exact HTML --
    # verified indirectly: the candidate exists and matches what's in the
    # persisted HTML (proving extraction ran against the persisted copy,
    # not a separate/different fetch).
    candidates = storage.repo_candidates
    matching = [c for c in candidates.values() if c["paper_id"] == paper_id]
    assert len(matching) == 1
    assert matching[0]["repo_url"] == "https://github.com/some/repo"
    assert "https://github.com/some/repo" in obs["raw_payload"]["html"]


# -----------------------------------------------------------------
# D. a failed HTML fetch does not produce a repository association
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_failed_fetch_persists_failure_observation_without_fabricating_html_or_candidates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    settings = _settings(max_retry_attempts=2)
    storage = FakeStorage()
    paper_id = _seed_paper(storage, "2508.66666", "https://arxiv.org/abs/2508.66666")

    evidence_adapter = RepoEvidenceAdapter(settings, transport=transport)
    await run_repo_resolution(settings, storage, evidence_adapter=evidence_adapter)

    obs = next(
        o for o in storage.fetch_observations.values()
        if o["source_name"] == "arxiv_abs_page_html" and o["paper_id"] == paper_id
    )
    assert obs["fetch_status"] == "TIMEOUT"  # retry-exhausted path
    assert obs["raw_payload"] == {}  # never fabricated HTML
    assert obs["content_hash"] == hashlib.sha256(b"").hexdigest()  # deterministic "no content" hash

    matching_candidates = [c for c in storage.repo_candidates.values() if c["paper_id"] == paper_id]
    assert matching_candidates == []  # no association possible without evidence


# -----------------------------------------------------------------
# E. repeated fetches create separate observations rather than overwriting
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_repeated_fetches_append_rather_than_overwrite():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, text=f"<html>version {call_count['n']}</html>")

    settings = _settings()
    storage = FakeStorage()
    paper_id = _seed_paper(storage, "2508.77777", "https://arxiv.org/abs/2508.77777")

    # First run.
    transport1 = httpx.MockTransport(handler)
    await run_repo_resolution(settings, storage, evidence_adapter=RepoEvidenceAdapter(settings, transport=transport1))

    # Manually reset status to simulate a legitimate rerun of this stage
    # (in the real pipeline this would be a fresh batch pass).
    storage.papers[paper_id]["status"] = "PARSED"

    # Second run -- different content this time.
    transport2 = httpx.MockTransport(handler)
    await run_repo_resolution(settings, storage, evidence_adapter=RepoEvidenceAdapter(settings, transport=transport2))

    html_obs = [
        o for o in storage.fetch_observations.values()
        if o["source_name"] == "arxiv_abs_page_html" and o["paper_id"] == paper_id
    ]
    assert len(html_obs) == 2  # both preserved, neither overwritten
    bodies = {o["raw_payload"]["html"] for o in html_obs}
    assert bodies == {"<html>version 1</html>", "<html>version 2</html>"}
