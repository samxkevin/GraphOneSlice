"""
Fetches the raw HTML of an arXiv abstract page. This is the ONLY module
that performs the network I/O for repo-evidence extraction -- parsing
is entirely delegated to the pure src/parsers/repo_evidence_parser.py.

Reuses the same retry/backoff abstraction as arxiv_adapter.py and
github_client.py (src/pipeline/retry.py) rather than inventing a second
retry system, per the existing project conventions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

import httpx

from src.config.settings import Settings
from src.pipeline.logging_config import get_logger
from src.pipeline.retry import NonRetryableError, RetryConfig, RetryExhaustedError, retry_with_backoff

logger = get_logger(__name__)


@dataclass
class AbsPageFetchResult:
    arxiv_abs_url: str
    html: str | None
    content_hash: str
    fetched_at: datetime
    http_status: int | None
    fetch_status: str  # 'OK' | 'ERROR' | 'TIMEOUT' -- matches FetchStatus enum values


class RepoEvidenceAdapter:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        """transport: optional override for tests (httpx.MockTransport).
        Never set in production -- defaults to a real connection."""
        self._settings = settings
        self._transport = transport
        self._retry_config = RetryConfig(
            max_attempts=settings.max_retry_attempts,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
            backoff_max_seconds=settings.retry_backoff_max_seconds,
            jitter_seconds=settings.retry_jitter_seconds,
        )

    async def fetch_abs_page(self, arxiv_abs_url: str) -> AbsPageFetchResult:
        """
        Fetches the abs page HTML. Follows the same error contract as
        the rest of the pipeline: a fetch failure is a normal, logged
        outcome (fetch_status != 'OK'), never an unhandled exception
        that would take down the whole batch, and never a reason to
        fabricate a result.
        """

        async def _do_fetch() -> httpx.Response:
            async with httpx.AsyncClient(
                timeout=self._settings.arxiv_http_timeout_seconds,
                transport=self._transport,
            ) as client:
                resp = await client.get(arxiv_abs_url)
                if resp.status_code == 429:
                    raise Exception(f"arxiv abs page 429 at {arxiv_abs_url}")
                if resp.status_code >= 500:
                    raise Exception(f"arxiv abs page server error {resp.status_code} at {arxiv_abs_url}")
                if resp.status_code >= 400:
                    raise NonRetryableError(f"arxiv abs page client error {resp.status_code} at {arxiv_abs_url}")
                return resp

        try:
            resp = await retry_with_backoff(_do_fetch, self._retry_config)
        except NonRetryableError as exc:
            logger.warning(
                "abs page fetch non-retryable failure",
                extra={"stage": "repo_evidence_fetch", "status": "ERROR", "source": arxiv_abs_url},
            )
            return AbsPageFetchResult(
                arxiv_abs_url=arxiv_abs_url, html=None,
                content_hash=hashlib.sha256(b"").hexdigest(),  # no content received -- not fabricated
                fetched_at=datetime.now(timezone.utc), http_status=None, fetch_status="ERROR",
            )
        except RetryExhaustedError as exc:
            logger.warning(
                "abs page fetch retries exhausted",
                extra={"stage": "repo_evidence_fetch", "status": "TIMEOUT", "source": arxiv_abs_url},
            )
            return AbsPageFetchResult(
                arxiv_abs_url=arxiv_abs_url, html=None,
                content_hash=hashlib.sha256(b"").hexdigest(),
                fetched_at=datetime.now(timezone.utc), http_status=None, fetch_status="TIMEOUT",
            )

        return AbsPageFetchResult(
            arxiv_abs_url=arxiv_abs_url,
            html=resp.text,
            content_hash=hashlib.sha256(resp.content).hexdigest(),
            fetched_at=datetime.now(timezone.utc),
            http_status=resp.status_code,
            fetch_status="OK",
        )
