from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import json
import random
from typing import Any

import httpx


class FailureClass(str, Enum):
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED_JSON = "malformed_json"
    HTTP_ERROR = "http_error"


class SourceFetchError(RuntimeError):
    def __init__(self, failure_class: FailureClass, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.failure_class = failure_class
        self.status_code = status_code


@dataclass(frozen=True)
class HttpRetryConfig:
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    jitter_seconds: float = 0.25


@dataclass(frozen=True)
class JsonResponse:
    data: Any
    url: str
    status_code: int
    headers: dict[str, str]


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def classify_status(status_code: int) -> FailureClass:
    if status_code == 429:
        return FailureClass.RATE_LIMITED
    if status_code == 413:
        return FailureClass.PAYLOAD_TOO_LARGE
    if status_code == 404:
        return FailureClass.NOT_FOUND
    if status_code == 403:
        return FailureClass.FORBIDDEN
    return FailureClass.HTTP_ERROR


class JsonHttpClient:
    """Small async JSON client with bounded retries and explicit failures."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        retry: HttpRetryConfig | None = None,
        headers: dict[str, str] | None = None,
        verify: str | bool = "/etc/ssl/certs/ca-certificates.crt",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._timeout = timeout_seconds
        self._retry = retry or HttpRetryConfig()
        self._headers = headers or {}
        self._verify = verify
        self._transport = transport

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> JsonResponse:
        last_error: SourceFetchError | None = None
        attempts = self._retry.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._headers,
                    verify=self._verify,
                    transport=self._transport,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_error = SourceFetchError(FailureClass.TIMEOUT, f"timeout requesting {url}")
                if attempt >= attempts:
                    raise last_error from exc
                await self._sleep(attempt)
                continue
            except httpx.RequestError as exc:
                last_error = SourceFetchError(FailureClass.NETWORK, f"network failure requesting {url}: {exc}")
                if attempt >= attempts:
                    raise last_error from exc
                await self._sleep(attempt)
                continue

            status = response.status_code
            if status in RETRYABLE_STATUSES:
                last_error = SourceFetchError(classify_status(status), f"HTTP {status} requesting {response.url}", status_code=status)
                if attempt >= attempts:
                    raise last_error
                retry_after = response.headers.get("Retry-After")
                await self._sleep(attempt, retry_after=retry_after)
                continue
            if status >= 400:
                raise SourceFetchError(classify_status(status), f"HTTP {status} requesting {response.url}", status_code=status)

            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise SourceFetchError(FailureClass.MALFORMED_JSON, f"malformed JSON from {response.url}", status_code=status) from exc

            return JsonResponse(data=data, url=str(response.url), status_code=status, headers=dict(response.headers))

        assert last_error is not None
        raise last_error

    async def _sleep(self, attempt: int, retry_after: str | None = None) -> None:
        delay: float | None = None
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = None
        if delay is None:
            delay = min(self._retry.backoff_base_seconds * (2 ** (attempt - 1)), self._retry.backoff_max_seconds)
            delay += random.uniform(0, self._retry.jitter_seconds)
        await asyncio.sleep(delay)
