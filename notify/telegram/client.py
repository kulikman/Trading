"""Telegram Bot API (T18, минимум для запуска): отправка сообщения в чат заказчика.

TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID — из окружения; нет — сообщения не отправляются (разработка).
Ошибка отправки не содержит адреса запроса: в нём токен бота.
"""

import os

import httpx

from adapters.health import mark_error, mark_ok

API = "https://api.telegram.org"
SOURCE = "telegram"
TIMEOUT_SECONDS = 20.0


class TelegramError(RuntimeError):
    """Telegram не принял сообщение."""


class TelegramClient:
    def __init__(
        self, token: str, chat_id: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._transport = transport

    @classmethod
    def from_env(cls) -> "TelegramClient | None":
        """Клиент из окружения; бот не настроен — None."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        return cls(token, chat_id) if token and chat_id else None

    def send(self, text: str) -> int:
        """Отправить сообщение; вернуть его id в чате."""
        with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as http:
            try:
                response = http.post(
                    f"{API}/bot{self._token}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text},
                )
            except httpx.HTTPError as error:
                mark_error(SOURCE, type(error).__name__)
                raise TelegramError(f"sendMessage: {type(error).__name__}") from None
        body = response.json() if response.content else {}
        if response.status_code != 200 or not body.get("ok"):
            description = body.get("description", "") if isinstance(body, dict) else ""
            detail = f"sendMessage: HTTP {response.status_code} {description}".strip()
            mark_error(SOURCE, detail)
            raise TelegramError(detail)
        mark_ok(SOURCE)
        return int(body["result"]["message_id"])
