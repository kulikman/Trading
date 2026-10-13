import logging
import os
import time
import uuid
from collections.abc import Iterator

import pytest
import redis

from adapters.cache import MemoryCache, RedisCache
from core.config import ConfigError, load_config


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_memory_cache_returns_value_until_ttl_expires() -> None:
    clock = FakeClock()
    cache = MemoryCache(clock)
    cache.set("k", b"v", ttl_seconds=10)
    assert cache.get("k") == b"v"
    clock.now += 10
    assert cache.get("k") is None
    assert cache.get("missing") is None


@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    url = os.environ.get("REDIS_URL")
    if not url:
        pytest.fail("REDIS_URL is not set. Cache tests need Redis: `make db-up && make test`.")
    client = redis.Redis.from_url(url)
    yield client
    client.close()


def test_redis_cache_roundtrip_and_ttl(redis_client: redis.Redis) -> None:
    prefix = f"test-{uuid.uuid4().hex}:"
    cache = RedisCache(redis_client, prefix=prefix)
    cache.set("k", b"v", ttl_seconds=30)
    assert cache.get("k") == b"v"
    ttl = redis_client.ttl(prefix + "k")
    assert isinstance(ttl, int)
    assert 0 < ttl <= 30
    assert cache.get("missing") is None
    redis_client.delete(prefix + "k")


def test_redis_outage_is_a_fast_logged_cache_miss(caplog: pytest.LogCaptureFixture) -> None:
    timeout = load_config().sources.redis.timeout_seconds
    cache = RedisCache.connect("redis://127.0.0.1:1/0", timeout)
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="adapters.cache"):
        assert cache.get("k") is None
        cache.set("k", b"v", ttl_seconds=5)
    # Без повторов redis-py: две операции укладываются в два таймаута, а не в секунды backoff.
    assert time.monotonic() - started < 2 * timeout + 1
    assert [r.getMessage() for r in caplog.records] == ["cache get failed", "cache set failed"]


def test_redis_cache_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert isinstance(RedisCache.from_env(timeout_seconds=0.5), RedisCache)
    monkeypatch.delenv("REDIS_URL")
    with pytest.raises(ConfigError, match="REDIS_URL"):
        RedisCache.from_env(timeout_seconds=0.5)
