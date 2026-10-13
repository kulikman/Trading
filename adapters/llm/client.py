"""Обёртка Claude API: текст → объект по pydantic-схеме (SPEC §6; CLAUDE.md правила 2 и 11).

LLM только извлекает числовые признаки и пишет резюме — не считает вероятности и не решает.
В запрос уходят только инструкция и текст документа: ни секретов, ни позиций, ни капитала.
"""

import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from typing import Any

import anthropic
from anthropic import transform_schema
from anthropic.types.beta import BetaMessage
from pydantic import BaseModel, ValidationError

from adapters.api_model import require_env
from adapters.errors import DataError
from core.config.sources import LlmSettings

logger = logging.getLogger(__name__)

SOURCE = "llm"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
SECRET_ENV_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)
MIN_SECRET_LENGTH = 8

CreateMessage = Callable[..., object]


def anthropic_api_key() -> str:
    """ANTHROPIC_API_KEY из окружения."""
    return require_env("ANTHROPIC_API_KEY")


class SecretInPromptError(ValueError):
    """В текст для LLM попало значение секретной переменной окружения — ошибка кода, не данных."""


class _InvalidOutput(Exception):
    pass


class LlmClient:
    """Один метод — extract. Невалидный ответ → 1 повтор → DataError (SPEC §6)."""

    def __init__(
        self,
        create: CreateMessage,
        settings: LlmSettings,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._create = create
        self._settings = settings
        self._env = os.environ if env is None else env

    @classmethod
    def create_default(cls, settings: LlmSettings, api_key: str) -> "LlmClient":
        client = anthropic.Anthropic(api_key=api_key)
        return cls(client.beta.messages.create, settings)

    def extract[M: BaseModel](self, *, instructions: str, text: str, schema: type[M]) -> M:
        """Извлечь объект schema из text по instructions (структурированный вывод по JSON-схеме)."""
        self._guard_secrets(instructions, text)
        request: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",  # при отказе модели API повторит запрос на резервной модели
            "system": instructions,
            "messages": [{"role": "user", "content": text}],
            "output_config": {
                "effort": self._settings.effort,
                "format": {"type": "json_schema", "schema": transform_schema(schema)},
            },
        }
        last_error = "no attempts"
        for attempt in range(1, self._settings.max_attempts + 1):
            response = self._call(request)
            if response.stop_reason == "refusal":
                category = response.stop_details.category if response.stop_details else None
                raise DataError(SOURCE, f"model refused (category={category})")
            try:
                return _parse(response, schema)
            except _InvalidOutput as exc:
                last_error = str(exc)
                logger.warning(
                    "llm output rejected", extra={"attempt": attempt, "schema": schema.__name__}
                )
        raise DataError(
            SOURCE,
            f"{schema.__name__}: invalid output after {self._settings.max_attempts} "
            f"attempts: {last_error}",
        )

    def _call(self, request: dict[str, Any]) -> BetaMessage:
        try:
            response = self._create(**request)
        except anthropic.APIConnectionError as exc:
            raise DataError(SOURCE, f"connection error: {type(exc).__name__}") from exc
        except anthropic.RateLimitError as exc:
            raise DataError(SOURCE, "rate limited (429)") from exc
        except anthropic.APIStatusError as exc:
            raise DataError(SOURCE, f"HTTP {exc.status_code}") from exc
        if not isinstance(response, BetaMessage):
            raise DataError(SOURCE, f"unexpected response type {type(response).__name__}")
        return response

    def _guard_secrets(self, *parts: str) -> None:
        prompt = "\n".join(parts)
        for name, value in self._env.items():
            if SECRET_ENV_NAME.search(name) and len(value) >= MIN_SECRET_LENGTH and value in prompt:
                raise SecretInPromptError(f"prompt contains the value of {name}")


def _parse[M: BaseModel](response: BetaMessage, schema: type[M]) -> M:
    if response.stop_reason == "max_tokens":
        raise _InvalidOutput("truncated at max_tokens")
    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise _InvalidOutput("no text block")
    try:
        return schema.model_validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise _InvalidOutput(f"not JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise _InvalidOutput(f"schema mismatch: {exc.error_count()} error(s)") from exc
