import httpx
import pytest

from src.config.settings import Settings
from src.github_client.client import GithubClient
from src.models.schemas import GithubApiStatus


def _settings(**overrides) -> Settings:
    base = dict(
        database_url="postgresql://u:p@localhost/db",
        github_token="fake-token",
        max_retry_attempts=2,
        retry_backoff_base_seconds=0.01,
        retry_backoff_max_seconds=0.02,
        retry_jitter_seconds=0.01,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_verify_existing_repo_returns_ok_and_stars():
    # Outcome class: successfully resolved GitHub repository
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"stargazers_count": 4242})

    transport = httpx.MockTransport(handler)
    client = GithubClient(_settings(), transport=transport)

    snapshot = await client.verify_and_get_stars("https://github.com/org/repo")
    assert snapshot.exists_verified is True
    assert snapshot.stargazers_count == 4242
    assert snapshot.api_status == GithubApiStatus.OK


@pytest.mark.asyncio
async def test_verify_deleted_repo_returns_not_found():
    # Outcome class: unavailable/deleted GitHub repository
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    client = GithubClient(_settings(), transport=transport)

    snapshot = await client.verify_and_get_stars("https://github.com/org/gone")
    assert snapshot.exists_verified is False
    assert snapshot.stargazers_count is None
    assert snapshot.api_status == GithubApiStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_rate_limited_response_never_fabricates_stars():
    # Outcome class: retry/rate-limit handling path
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={"message": "rate limited"})

    transport = httpx.MockTransport(handler)
    client = GithubClient(_settings(max_retry_attempts=2), transport=transport)

    snapshot = await client.verify_and_get_stars("https://github.com/org/repo")
    assert snapshot.stargazers_count is None  # never guessed
    assert snapshot.api_status == GithubApiStatus.RATE_LIMITED
    assert call_count["n"] == 2  # bounded retries, exactly max_attempts


@pytest.mark.asyncio
async def test_unparseable_repo_url_returns_error_status():
    client = GithubClient(_settings())
    snapshot = await client.verify_and_get_stars("not-a-github-url")
    assert snapshot.exists_verified is False
    assert snapshot.api_status == GithubApiStatus.ERROR


@pytest.mark.asyncio
async def test_server_error_retries_then_reports_status_honestly():
    # Outcome class: transient failure exhausts retries -> reported honestly,
    # never silently treated as success
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = GithubClient(_settings(max_retry_attempts=3), transport=transport)

    snapshot = await client.verify_and_get_stars("https://github.com/org/flaky")
    assert snapshot.exists_verified is False
    assert snapshot.stargazers_count is None
    assert call_count["n"] == 3
