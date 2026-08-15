import pytest

from src.pipeline.retry import (
    NonRetryableError,
    RetryConfig,
    RetryExhaustedError,
    retry_with_backoff,
)


@pytest.mark.asyncio
async def test_succeeds_on_first_try():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        return "ok"

    result = await retry_with_backoff(fn, RetryConfig(max_attempts=3, backoff_base_seconds=0.01,
                                                        backoff_max_seconds=0.05, jitter_seconds=0.01))
    assert result == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("transient")
        return "ok"

    result = await retry_with_backoff(fn, RetryConfig(max_attempts=5, backoff_base_seconds=0.01,
                                                        backoff_max_seconds=0.05, jitter_seconds=0.01))
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_bounded_attempts_raises_retry_exhausted():
    # Documents: NEVER retry forever -- must be bounded per guardrails §12
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise Exception("always fails")

    with pytest.raises(RetryExhaustedError):
        await retry_with_backoff(fn, RetryConfig(max_attempts=3, backoff_base_seconds=0.01,
                                                    backoff_max_seconds=0.05, jitter_seconds=0.01))
    assert calls["n"] == 3  # exactly max_attempts, not more


@pytest.mark.asyncio
async def test_non_retryable_error_short_circuits_immediately():
    # e.g. invalid API key / malformed input -- must not waste retries
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise NonRetryableError("bad credentials")

    with pytest.raises(NonRetryableError):
        await retry_with_backoff(fn, RetryConfig(max_attempts=5, backoff_base_seconds=0.01,
                                                    backoff_max_seconds=0.05, jitter_seconds=0.01))
    assert calls["n"] == 1  # no retry attempted at all
