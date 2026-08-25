import pytest
import httpx

from src.ai_orbit.utils.http import FailureClass, HttpRetryConfig, JsonHttpClient, SourceFetchError


@pytest.mark.asyncio
async def test_retryable_429_is_bounded_and_eventually_succeeds():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(429, json={"message": "rate limited"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = JsonHttpClient(
        retry=HttpRetryConfig(max_attempts=3, backoff_base_seconds=0, jitter_seconds=0),
        transport=httpx.MockTransport(handler),
        verify=False,
    )
    response = await client.get_json("https://example.com/data")
    assert response.data == {"ok": True}
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_retry_exhaustion_does_not_loop_forever():
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"message": "temporary"}, request=request)

    client = JsonHttpClient(
        retry=HttpRetryConfig(max_attempts=2, backoff_base_seconds=0, jitter_seconds=0),
        transport=httpx.MockTransport(handler),
        verify=False,
    )
    with pytest.raises(SourceFetchError) as exc_info:
        await client.get_json("https://example.com/data")
    assert calls["count"] == 2
    assert exc_info.value.failure_class == FailureClass.HTTP_ERROR
