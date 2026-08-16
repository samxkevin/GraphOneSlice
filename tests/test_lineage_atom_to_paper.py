from pathlib import Path

import httpx
import pytest

from src.adapters.arxiv_adapter import ArxivAdapter
from src.config.settings import Settings
from src.pipeline.orchestrator import run_discovery_and_parse
from tests.fakes import FakeStorage

FIXTURES = Path(__file__).parent / "fixtures"


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql://u:p@localhost/db",
        arxiv_page_size=100,
        arxiv_max_results=100,  # exactly one page fetch -- keeps the test deterministic
        arxiv_request_delay_seconds=0.001,
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.02,
        retry_jitter_seconds=0.01,
    )
    base.update(overrides)
    return Settings(**base)


def _adapter_with_fixed_response(body: str, settings: Settings) -> ArxivAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    return ArxivAdapter(settings, transport=transport)


# -----------------------------------------------------------------
# A. successful arXiv observation becomes linked to the resulting paper
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_successful_observation_linked_to_both_resulting_papers():
    xml = (FIXTURES / "arxiv_two_valid_papers.xml").read_text()
    settings = _settings()
    storage = FakeStorage()
    adapter = _adapter_with_fixed_response(xml, settings)

    parsed_count = await run_discovery_and_parse(settings, storage, adapter=adapter)

    assert parsed_count == 2
    assert len(storage.fetch_observations) == 1  # one page fetch -> one observation
    observation_id = next(iter(storage.fetch_observations))
    assert len(storage.papers) == 2

    # Both papers must be linked to the SAME shared observation --
    # this is exactly the many-papers-per-one-observation case the
    # join table exists for.
    for paper_id in storage.papers:
        assert (paper_id, observation_id) in storage.paper_fetch_observations

    # The observation itself must retain the raw Atom XML -- not just a status.
    obs = storage.fetch_observations[observation_id]
    assert "atom_xml" in obs["raw_payload"]
    assert "2508.11111" in obs["raw_payload"]["atom_xml"]


@pytest.mark.asyncio
async def test_observations_never_identified_solely_by_url():
    # Two separate fetches to the exact same source_url must remain two
    # distinct, separately-linkable observation rows -- proving linkage
    # is by explicit id, not by matching source_url.
    xml = (FIXTURES / "arxiv_two_valid_papers.xml").read_text()
    settings = _settings()
    storage = FakeStorage()

    adapter1 = _adapter_with_fixed_response(xml, settings)
    await run_discovery_and_parse(settings, storage, adapter=adapter1)

    adapter2 = _adapter_with_fixed_response(xml, settings)
    await run_discovery_and_parse(settings, storage, adapter=adapter2)

    urls = {o["source_url"] for o in storage.fetch_observations.values()}
    assert len(urls) == 1  # identical URL both times
    assert len(storage.fetch_observations) == 2  # but two distinct observation rows


# -----------------------------------------------------------------
# B. malformed/unparseable observation can legitimately remain paper_id=NULL
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_malformed_observation_preserved_but_unlinked():
    settings = _settings()
    storage = FakeStorage()
    adapter = _adapter_with_fixed_response("<not valid xml at all", settings)

    parsed_count = await run_discovery_and_parse(settings, storage, adapter=adapter)

    assert parsed_count == 0
    # The raw evidence is still preserved -- never dropped just because
    # it couldn't be parsed.
    assert len(storage.fetch_observations) == 1
    # But nothing exists to link it to -- no papers, no link rows.
    assert len(storage.papers) == 0
    assert len(storage.paper_fetch_observations) == 0


# -----------------------------------------------------------------
# C. rerunning the same stage does not create an incorrect or
#    duplicate lineage relationship
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_link_paper_to_observation_is_idempotent_for_the_same_pair():
    storage = FakeStorage()
    from uuid import uuid4
    paper_id, obs_id = uuid4(), uuid4()

    await storage.link_paper_to_observation(paper_id, obs_id)
    await storage.link_paper_to_observation(paper_id, obs_id)  # exact same pair again

    assert len(storage.paper_fetch_observations) == 1  # no duplicate, matches ON CONFLICT DO NOTHING


@pytest.mark.asyncio
async def test_rerun_creates_new_observation_but_same_papers_correctly_linked():
    xml = (FIXTURES / "arxiv_two_valid_papers.xml").read_text()
    settings = _settings()
    storage = FakeStorage()

    adapter1 = _adapter_with_fixed_response(xml, settings)
    await run_discovery_and_parse(settings, storage, adapter=adapter1)

    adapter2 = _adapter_with_fixed_response(xml, settings)
    await run_discovery_and_parse(settings, storage, adapter=adapter2)

    # Still exactly 2 unique papers -- upsert_paper_discovered dedupes by
    # arxiv_id, a rerun must never create duplicate paper identities.
    assert len(storage.papers) == 2
    # Two distinct observations (append-only, both fetches really happened).
    assert len(storage.fetch_observations) == 2
    obs_ids = list(storage.fetch_observations.keys())

    # Each paper correctly linked to BOTH observations (it was genuinely
    # present in both fetches) -- and to nothing else.
    for paper_id in storage.papers:
        links_for_paper = {oid for (pid, oid) in storage.paper_fetch_observations if pid == paper_id}
        assert links_for_paper == set(obs_ids)

    # No cross-contamination: total link count is exactly papers x observations.
    assert len(storage.paper_fetch_observations) == 2 * 2
