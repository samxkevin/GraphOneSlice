"""
arXiv source adapter. Responsibility: discovery + fetch ONLY.
Produces raw FetchObservation objects. Does not parse into ParsedPaper
(that's paper_parser's job) and never calls into repo association,
GitHub, or storage directly -- those are separate stages.

Evidence: arXiv API is documented at export.arxiv.org, official rate
guidance is ~3 req/sec; we deliberately stay under that (config default
3.5s delay) since a real-world forum report found sustained 429s even
at compliant delays under concurrent load.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import httpx

from src.config.settings import Settings
from src.pipeline.logging_config import get_logger
from src.pipeline.retry import NonRetryableError, RetryConfig, retry_with_backoff

logger = get_logger(__name__)


class ArxivAdapter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._retry_config = RetryConfig(
            max_attempts=settings.max_retry_attempts,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
            backoff_max_seconds=settings.retry_backoff_max_seconds,
            jitter_seconds=settings.retry_jitter_seconds,
        )

    async def fetch_page(self, start: int, max_results: int) -> dict:
        """Fetch one page of arXiv Atom results. Returns a dict with
        raw_payload (the Atom XML as text, wrapped for JSONB storage),
        source_url, http_status, fetched_at, content_hash."""
        params = {
            "search_query": self._settings.arxiv_search_query,
            "start": start,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        source_url = self._settings.arxiv_api_base

        async def _do_fetch() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self._settings.arxiv_http_timeout_seconds) as client:
                resp = await client.get(source_url, params=params)
                if resp.status_code == 429:
                    raise Exception(f"arXiv 429 rate limited at start={start}")
                if resp.status_code >= 500:
                    raise Exception(f"arXiv server error {resp.status_code} at start={start}")
                if resp.status_code >= 400:
                    raise NonRetryableError(f"arXiv client error {resp.status_code} at start={start}")
                return resp

        resp = await retry_with_backoff(_do_fetch, self._retry_config)
        fetched_at = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(resp.content).hexdigest()

        # Respect the documented rate ceiling before the caller requests the next page.
        await asyncio.sleep(self._settings.arxiv_request_delay_seconds)

        return {
            "source_name": "arxiv",
            "source_url": f"{source_url}?start={start}&max_results={max_results}",
            "raw_payload": {"atom_xml": resp.text},
            "content_hash": content_hash,
            "fetched_at": fetched_at,
            "http_status": resp.status_code,
            "fetch_status": "OK",
        }

    async def discover_all(self) -> list[dict]:
        """Paginate through arXiv results up to arxiv_max_results,
        bounded and configurable -- not an unbounded crawl."""
        observations: list[dict] = []
        start = 0
        page_size = self._settings.arxiv_page_size
        while start < self._settings.arxiv_max_results:
            try:
                obs = await self.fetch_page(start, page_size)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "arxiv page fetch failed",
                    extra={"stage": "arxiv_discovery", "status": "ERROR",
                           "error_type": type(exc).__name__},
                )
                break
            observations.append(obs)
            # Stop if a page returns no entries (heuristic: very short payload)
            if "<entry>" not in obs["raw_payload"]["atom_xml"]:
                break
            start += page_size
        return observations
