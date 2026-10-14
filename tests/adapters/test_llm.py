import json
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage
from pydantic import BaseModel, Field

from adapters.errors import DataError
from adapters.llm.client import FALLBACK_BETA, LlmClient, SecretInPromptError, anthropic_api_key
from core.config import ConfigError, load_config
from core.config.sources import LlmSettings


class Guidance(BaseModel):
    """Пример схемы признаков: только числа."""

    direction: int = Field(ge=-1, le=1)
    management_tone: float = Field(ge=-1, le=1)


def message(text: str | None, stop_reason: str = "end_turn", **extra: Any) -> BetaMessage:
    content = [] if text is None else [{"type": "text", "text": text}]
    return BetaMessage.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            **extra,
        }
    )


class FakeMessages:
    """Подмена client.beta.messages.create: отдаёт ответы по очереди и запоминает запросы."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def settings() -> LlmSettings:
    return load_config().sources.llm


def llm(settings: LlmSettings, fake: FakeMessages, env: dict[str, str] | None = None) -> LlmClient:
    return LlmClient(fake, settings, env={} if env is None else env)


VALID = json.dumps({"direction": 1, "management_tone": 0.4})


def test_valid_structured_output(settings: LlmSettings) -> None:
    fake = FakeMessages(message(VALID))
    result = llm(settings, fake).extract(
        instructions="Extract guidance.", text="Raised FY guide.", schema=Guidance
    )
    assert result == Guidance(direction=1, management_tone=0.4)
    request = fake.calls[0]
    assert request["model"] == settings.model
    assert request["system"] == "Extract guidance."
    assert request["messages"] == [{"role": "user", "content": "Raised FY guide."}]
    assert request["betas"] == [FALLBACK_BETA]
    assert request["fallbacks"] == "default"
    output = request["output_config"]
    assert output["effort"] == settings.effort
    assert output["format"]["type"] == "json_schema"
    assert output["format"]["schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "bad",
    [
        message('{"direction": 5, "management_tone": 0.1}'),  # не по схеме (вне диапазона)
        message("not json"),
        message(None),  # нет текстового блока
        message(VALID[:10], stop_reason="max_tokens"),  # обрезано лимитом токенов
    ],
    ids=["schema-mismatch", "not-json", "no-text", "truncated"],
)
def test_invalid_output_is_retried_once_then_succeeds(
    settings: LlmSettings, bad: BetaMessage
) -> None:
    fake = FakeMessages(bad, message(VALID))
    assert llm(settings, fake).extract(instructions="i", text="t", schema=Guidance).direction == 1
    assert len(fake.calls) == 2


def test_invalid_twice_is_data_error(settings: LlmSettings) -> None:
    fake = FakeMessages(message('{"direction": 9}'), message("still not json"))
    with pytest.raises(
        DataError, match=r"Guidance: invalid output after 2 attempts: not JSON"
    ) as exc:
        llm(settings, fake).extract(instructions="i", text="t", schema=Guidance)
    assert exc.value.source == "llm"
    assert len(fake.calls) == settings.max_attempts


def test_refusal_is_data_error_without_retry(settings: LlmSettings) -> None:
    refused = message(
        None,
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": "cyber", "explanation": "x"},
    )
    fake = FakeMessages(refused)
    with pytest.raises(DataError, match="model refused \\(category=cyber\\)"):
        llm(settings, fake).extract(instructions="i", text="t", schema=Guidance)
    assert len(fake.calls) == 1


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    ("error", "message_text"),
    [
        (anthropic.APIConnectionError(request=_request()), "connection error"),
        (
            anthropic.RateLimitError(
                "slow down", response=httpx2.Response(429, request=_request()), body=None
            ),
            "rate limited",
        ),
        (
            anthropic.InternalServerError(
                "boom", response=httpx2.Response(500, request=_request()), body=None
            ),
            "HTTP 500",
        ),
    ],
    ids=["connection", "rate-limit", "server"],
)
def test_api_errors_become_data_errors(
    settings: LlmSettings, error: Exception, message_text: str
) -> None:
    with pytest.raises(DataError, match=message_text):
        llm(settings, FakeMessages(error)).extract(instructions="i", text="t", schema=Guidance)


def test_unexpected_response_type(settings: LlmSettings) -> None:
    with pytest.raises(DataError, match="unexpected response type"):
        llm(settings, FakeMessages("stream?")).extract(instructions="i", text="t", schema=Guidance)


def test_secret_in_prompt_is_refused_before_sending(settings: LlmSettings) -> None:
    env = {"MASSIVE_API_KEY": "fakefakefakefake", "HOME": "/Users/x", "SHORT_TOKEN": "abc"}
    fake = FakeMessages(message(VALID))
    client = llm(settings, fake, env)
    with pytest.raises(SecretInPromptError, match="MASSIVE_API_KEY"):
        client.extract(instructions="i", text="leak fakefakefakefake here", schema=Guidance)
    assert fake.calls == []  # ничего не отправлено
    # обычные переменные и слишком короткие значения не считаются секретами
    assert (
        client.extract(instructions="path /Users/x abc", text="t", schema=Guidance).direction == 1
    )


def test_create_default_wires_sdk_client(settings: LlmSettings) -> None:
    client = LlmClient.create_default(settings, api_key="sk-test-not-used")
    assert isinstance(client, LlmClient)


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert anthropic_api_key() == "k"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        anthropic_api_key()
