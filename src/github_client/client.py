"""
GitHub repository verification client. Sole responsibility: given a
repo_url, confirm it exists and fetch its CURRENT stargazers_count
directly from the GitHub REST API. Never returns a star count that
wasn't just observed from a successful API response.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx

from src.config.settings import Settings
from src.models.schemas import GithubApiStatus, GithubSnapshot
from src.pipeline.logging_config import get_logger
from src.pipeline.retry import NonRetryableError, RetryConfig, retry_with_backoff

logger = get_logger(__name__)

_REPO_URL_RE = re.compile(r"github\.com/([^/]+)/([^/#?]+)")


class GithubClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        """
        transport: optional httpx transport override, used by tests to
        inject httpx.MockTransport without any real network access.
        Production code never sets this -- defaults to a real connection.
        """
        self._settings = settings
        self._transport = transport
        self._semaphore = asyncio.Semaphore(settings.github_max_concurrency)
        self._retry_config = RetryConfig(
            max_attempts=settings.max_retry_attempts,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
            backoff_max_seconds=settings.retry_backoff_max_seconds,
            jitter_seconds=settings.retry_jitter_seconds,
        )

    @staticmethod
    def _parse_owner_repo(repo_url: str) -> tuple[str, str] | None:
        match = _REPO_URL_RE.search(repo_url)
        if not match:
            return None
        owner, repo = match.group(1), match.group(2).removesuffix(".git")
        return owner, repo

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers

    async def verify_and_get_stars(self, repo_url: str) -> GithubSnapshot:
        """Returns a GithubSnapshot. NOT_FOUND (404) and RATE_LIMITED are
        valid, non-exceptional outcomes -- they produce a snapshot with
        exists_verified=False / stargazers_count=None, not a crash."""
        parsed = self._parse_owner_repo(repo_url)
        if parsed is None:
            return GithubSnapshot(
                repo_url=repo_url,
                exists_verified=False,
                stargazers_count=None,
                stars_fetched_at=datetime.now(timezone.utc),
                api_status=GithubApiStatus.ERROR,
            )
        owner, repo = parsed
        url = f"{self._settings.github_api_base}/repos/{owner}/{repo}"

        async def _do_fetch() -> httpx.Response:
            async with self._semaphore:
                async with httpx.AsyncClient(
                    timeout=self._settings.github_http_timeout_seconds,
                    transport=self._transport,
                ) as client:
                    resp = await client.get(url, headers=self._headers())
                    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                        raise Exception("github rate limited (403 secondary/primary limit)")
                    if resp.status_code == 429:
                        raise Exception("github rate limited (429)")
                    if resp.status_code >= 500:
                        raise Exception(f"github server error {resp.status_code}")
                    return resp

        def _retry_after(exc: Exception) -> float | None:
            # We don't have access to headers inside the exception here in this
            # minimal version; a fuller implementation would attach headers to
            # the exception object. Falls back to computed backoff.
            return None

        try:
            resp = await retry_with_backoff(_do_fetch, self._retry_config, _retry_after)
        except NonRetryableError:
            return GithubSnapshot(
                repo_url=repo_url, exists_verified=False, stargazers_count=None,
                stars_fetched_at=datetime.now(timezone.utc), api_status=GithubApiStatus.ERROR,
            )
        except Exception:  # noqa: BLE001 -- retry exhausted
            return GithubSnapshot(
                repo_url=repo_url, exists_verified=False, stargazers_count=None,
                stars_fetched_at=datetime.now(timezone.utc), api_status=GithubApiStatus.RATE_LIMITED,
            )

        fetched_at = datetime.now(timezone.utc)
        if resp.status_code == 404:
            return GithubSnapshot(
                repo_url=repo_url, exists_verified=False, stargazers_count=None,
                stars_fetched_at=fetched_at, api_status=GithubApiStatus.NOT_FOUND,
            )
        if resp.status_code != 200:
            return GithubSnapshot(
                repo_url=repo_url, exists_verified=False, stargazers_count=None,
                stars_fetched_at=fetched_at, api_status=GithubApiStatus.ERROR,
            )

        data = resp.json()
        stars = data.get("stargazers_count")
        return GithubSnapshot(
            repo_url=repo_url,
            exists_verified=True,
            stargazers_count=stars,
            stars_fetched_at=fetched_at,
            api_status=GithubApiStatus.OK,
        )
