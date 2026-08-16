import httpx
import pytest

from src.adapters.repo_evidence_adapter import RepoEvidenceAdapter
from src.config.settings import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql://u:p@localhost/db",
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.02,
        retry_jitter_seconds=0.01,
        arxiv_http_timeout_seconds=1.0,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_successful_fetch_returns_html():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>ok</html>")

    transport = httpx.MockTransport(handler)
    adapter = RepoEvidenceAdapter(_settings(), transport=transport)

    result = await adapter.fetch_abs_page("https://arxiv.org/abs/2508.00001")
    assert result.fetch_status == "OK"
    assert result.html == "<html>ok</html>"
    assert result.http_status == 200


# -----------------------------------------------------------------
# H. HTTP failure -- must follow the existing bounded-retry contract,
#    never crash the caller, never fabricate HTML.
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_persistent_server_error_exhausts_retries_and_reports_timeout_status():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    adapter = RepoEvidenceAdapter(_settings(max_retry_attempts=3), transport=transport)

    result = await adapter.fetch_abs_page("https://arxiv.org/abs/2508.00002")
    assert result.html is None
    assert result.fetch_status == "TIMEOUT"  # retry-exhausted path
    assert call_count["n"] == 3  # bounded, exactly max_attempts, no infinite retry


@pytest.mark.asyncio
async def test_client_error_404_is_non_retryable_and_fails_fast():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    adapter = RepoEvidenceAdapter(_settings(max_retry_attempts=5), transport=transport)

    result = await adapter.fetch_abs_page("https://arxiv.org/abs/2508.00003")
    assert result.html is None
    assert result.fetch_status == "ERROR"
    assert call_count["n"] == 1  # non-retryable -- no wasted retry attempts
