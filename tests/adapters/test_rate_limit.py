import httpx
import pytest

from adapters.cache import MemoryCache
from adapters.http import JsonHttpClient, RateLimiter, RetryPolicy


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_limiter_waits_only_when_window_is_full() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 60, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter()
        clock.now += 1
    assert clock.sleeps == []
    limiter()  # 4-й запрос в окне: ждать, пока выйдет первый (отправлен в t=0)
    assert clock.sleeps == [57.0]
    assert clock.now == 60.0


def test_rate_limiter_forgets_requests_older_than_period() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 10, clock=clock, sleep=clock.sleep)
    limiter()
    limiter()
    clock.now = 10.0
    limiter()
    limiter()
    assert clock.sleeps == []


@pytest.mark.parametrize(("requests", "period"), [(0, 60), (1, 0)])
def test_rate_limiter_rejects_bad_limits(requests: int, period: float) -> None:
    with pytest.raises(ValueError, match="rate limit"):
        RateLimiter(requests, period)


def test_throttle_runs_per_network_attempt_not_for_cache_hits() -> None:
    calls: list[str] = []
    responses = iter([httpx.Response(429), httpx.Response(200, json={"ok": True})])
    client = JsonHttpClient(
        source="test",
        base_url="https://api.example.com",
        timeout_seconds=1,
        retry=RetryPolicy(max_attempts=2, backoff_base_seconds=0),
        cache=MemoryCache(),
        transport=httpx.MockTransport(lambda _: next(responses)),
        sleep=lambda _: None,
        throttle=lambda: calls.append("sent"),
    )
    assert client.get_json("/x", ttl_seconds=60) == {"ok": True}
    assert client.get_json("/x", ttl_seconds=60) == {"ok": True}  # из кэша
    assert calls == ["sent", "sent"]  # повтор после 429 — тоже запрос к лимиту
