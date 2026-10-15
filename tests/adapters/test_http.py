import logging
from collections.abc import Callable

import httpx
import pytest

from adapters.cache import MemoryCache
from adapters.errors import DataError
from adapters.health import drain
from adapters.http import JsonHttpClient, RetryPolicy

SECRET = "secret-test-key"  # noqa: S105 — fake key for the log-leak test
Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses[min(len(self.requests), len(self.responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item


def make_client(
    handler: Handler, *, cache: MemoryCache | None = None, attempts: int = 3
) -> tuple[JsonHttpClient, list[float]]:
    sleeps: list[float] = []
    client = JsonHttpClient(
        source="test",
        base_url="https://api.example.com",
        headers={"Authorization": f"Bearer {SECRET}"},
        timeout_seconds=1,
        retry=RetryPolicy(max_attempts=attempts, backoff_base_seconds=0.5),
        cache=cache,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    return client, sleeps


def ok(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_success_parses_json_and_sends_auth_header() -> None:
    recorder = Recorder([ok({"status": "OK"})])
    client, sleeps = make_client(recorder)
    assert client.get_json("/v1/x", {"flag": True, "n": 5}) == {"status": "OK"}
    request = recorder.requests[0]
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert request.url.params["flag"] == "true"
    assert sleeps == []


def test_retries_on_429_with_backoff() -> None:
    recorder = Recorder([httpx.Response(429), ok({"status": "OK"})])
    client, sleeps = make_client(recorder)
    assert client.get_json("/v1/x") == {"status": "OK"}
    assert sleeps == [0.5]


def test_gives_up_after_max_attempts_on_5xx() -> None:
    recorder = Recorder([httpx.Response(503, text="busy")])
    client, sleeps = make_client(recorder)
    with pytest.raises(DataError, match="HTTP 503") as exc_info:
        client.get_json("/v1/x")
    assert exc_info.value.source == "test"
    assert len(recorder.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_client_error_is_not_retried() -> None:
    recorder = Recorder([httpx.Response(403, text="NOT_AUTHORIZED")])
    client, sleeps = make_client(recorder)
    with pytest.raises(DataError, match=r"HTTP 403.*NOT_AUTHORIZED"):
        client.get_json("/v1/x")
    assert len(recorder.requests) == 1
    assert sleeps == []


def test_network_error_is_retried_then_reported() -> None:
    recorder = Recorder([httpx.ConnectTimeout("timeout")])
    client, sleeps = make_client(recorder, attempts=2)
    with pytest.raises(DataError, match="ConnectTimeout"):
        client.get_json("/v1/x")
    assert sleeps == [0.5]


def test_network_error_then_success() -> None:
    recorder = Recorder([httpx.ReadTimeout("slow"), ok({"status": "OK"})])
    client, _ = make_client(recorder)
    assert client.get_json("/v1/x") == {"status": "OK"}


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="not json"), "invalid JSON"),
        (httpx.Response(200, json=[1, 2]), "expected a JSON object"),
    ],
)
def test_bad_body_is_data_error(response: httpx.Response, message: str) -> None:
    client, _ = make_client(Recorder([response]))
    with pytest.raises(DataError, match=message):
        client.get_json("/v1/x")


def test_cache_serves_repeat_request_without_network() -> None:
    recorder = Recorder([ok({"value": 1})])
    client, _ = make_client(recorder, cache=MemoryCache())
    assert client.get_json("/v1/x", {"a": 1}, ttl_seconds=60) == {"value": 1}
    assert client.get_json("/v1/x", {"a": 1}, ttl_seconds=60) == {"value": 1}
    assert len(recorder.requests) == 1


def test_zero_ttl_bypasses_cache() -> None:
    recorder = Recorder([ok({"value": 1})])
    client, _ = make_client(recorder, cache=MemoryCache())
    client.get_json("/v1/x", ttl_seconds=0)
    client.get_json("/v1/x", ttl_seconds=0)
    assert len(recorder.requests) == 2


def test_raw_response_is_logged_without_api_key(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = make_client(Recorder([ok({"status": "OK"})]))
    with caplog.at_level(logging.DEBUG, logger="adapters.http"):
        client.get_json("/v1/x")
    assert caplog.records, "raw response must be logged"
    assert all(SECRET not in str(record.__dict__) for record in caplog.records)
    client.close()


def test_get_text_without_validator_and_non_utf8_body() -> None:
    client, _ = make_client(Recorder([httpx.Response(200, content=b"a,b\n1,2\n")]))
    assert client.get_text("/v1/csv") == "a,b\n1,2\n"
    bad, _ = make_client(Recorder([httpx.Response(200, content=b"\xff\xfe\xfa")]))
    with pytest.raises(DataError, match="non-UTF-8"):
        bad.get_text("/v1/csv")


def test_secret_params_are_sent_but_redacted_everywhere(caplog: pytest.LogCaptureFixture) -> None:
    secret = "query-secret-123"  # noqa: S105 — fake key
    recorder = Recorder([httpx.Response(404, text=f"unknown key {secret}")])
    client = JsonHttpClient(
        source="test",
        base_url="https://api.example.com",
        secret_params={"token": secret},
        timeout_seconds=1,
        retry=RetryPolicy(max_attempts=1, backoff_base_seconds=0),
        transport=httpx.MockTransport(recorder),
    )
    with (
        caplog.at_level(logging.DEBUG, logger="adapters.http"),
        pytest.raises(DataError) as exc_info,
    ):
        client.get_json("/v1/x", {"a": 1})
    assert recorder.requests[0].url.params["token"] == secret
    assert secret not in str(exc_info.value)
    assert "token=***" in str(exc_info.value)
    assert all(secret not in str(record.__dict__) for record in caplog.records)


def test_network_answers_mark_source_health() -> None:
    drain()
    client, _ = make_client(Recorder([ok({"v": 1}), httpx.Response(404)]), cache=MemoryCache())
    client.get_json("/v1/x", ttl_seconds=60)
    client.get_json("/v1/x", ttl_seconds=60)  # из кэша — не отметка «жив»
    with pytest.raises(DataError):
        client.get_json("/v1/y")
    health = drain()["test"]
    assert health.last_ok_at is not None
    assert health.last_error_at is not None
    assert health.last_error is not None
    assert SECRET not in health.last_error
    assert drain() == {}  # после переноса в базу состояние в процессе очищено
