"""
Generic bounded retry with exponential backoff + jitter. Shared by any
component making external calls (arXiv, GitHub, Sheets). Never retries
forever; never retries non-retryable errors.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class NonRetryableError(Exception):
    """Raise this for errors that must not trigger a retry
    (bad credentials, malformed input, permanent 4xx other than 429)."""


class RetryExhaustedError(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class RetryConfig:
    max_attempts: int = 5
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    jitter_seconds: float = 0.5


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig,
    retry_after_seconds: Callable[[Exception], float | None] | None = None,
) -> T:
    """
    fn: the async operation to attempt.
    retry_after_seconds: optional callback that inspects a raised exception
        (e.g. one carrying a Retry-After header) and returns an explicit
        wait time, taking priority over computed backoff.
    """
    last_error: Exception | None = None
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await fn()
        except NonRetryableError:
            raise
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, classified by caller
            last_error = exc
            if attempt >= config.max_attempts:
                break
            wait = None
            if retry_after_seconds is not None:
                wait = retry_after_seconds(exc)
            if wait is None:
                backoff = min(
                    config.backoff_base_seconds * (2 ** (attempt - 1)),
                    config.backoff_max_seconds,
                )
                wait = backoff + random.uniform(0, config.jitter_seconds)
            await asyncio.sleep(wait)
    assert last_error is not None
    raise RetryExhaustedError(config.max_attempts, last_error)
