"""Telegram Bot API (T18): сообщения в чат заказчика, кнопки, приём нажатий (httpx, без aiogram:
aiogram 3 требует pydantic < 2.14, проект — 2.14).

TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID — из окружения; нет — сообщения не отправляются (разработка).
Ошибка отправки не содержит адреса запроса: в нём токен бота.
"""

import os

import httpx

from adapters.health import mark_error, mark_ok

API = "https://api.telegram.org"
SOURCE = "telegram"
TIMEOUT_SECONDS = 20.0
POLL_SECONDS = 25  # долгий опрос getUpdates

type Buttons = list[tuple[str, str]]  # (надпись, callback_data)


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

    @property
    def chat_id(self) -> str:
        return self._chat_id

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: Buttons | None = None,
        reply_to: int | None = None,
    ) -> int:
        """Отправить сообщение; silent — без звука (SPEC §12); вернуть его id в чате."""
        payload: dict[str, object] = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_notification": silent,
        }
        if buttons:
            payload["reply_markup"] = _keyboard(buttons)
        if reply_to is not None:
            payload["reply_parameters"] = {"message_id": reply_to}
        message_id = self._call("sendMessage", payload).get("message_id")
        if not isinstance(message_id, int):
            raise TelegramError("sendMessage: no message_id in the answer")
        return message_id

    def edit(self, message_id: int, text: str, *, buttons: Buttons | None = None) -> None:
        """Изменить текст и кнопки сообщения (одна карточка — одно сообщение, SPEC §12)."""
        payload: dict[str, object] = {
            "chat_id": self._chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": _keyboard(buttons or []),
        }
        self._call("editMessageText", payload)

    def updates(self, offset: int | None) -> list[dict[str, object]]:
        """Новые события бота (долгий опрос); offset — id последнего обработанного + 1."""
        payload: dict[str, object] = {
            "timeout": POLL_SECONDS,
            "allowed_updates": ["callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload, timeout=POLL_SECONDS + TIMEOUT_SECONDS)
        items = result.get("items", [])
        return [u for u in items if isinstance(u, dict)] if isinstance(items, list) else []

    def answer(self, callback_id: str, text: str) -> None:
        """Ответ на нажатие кнопки (всплывающая подсказка)."""
        self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200]})

    def _call(
        self, method: str, payload: dict[str, object], timeout: float = TIMEOUT_SECONDS
    ) -> dict[str, object]:
        with httpx.Client(transport=self._transport, timeout=timeout) as http:
            try:
                response = http.post(f"{API}/bot{self._token}/{method}", json=payload)
            except httpx.HTTPError as error:
                mark_error(SOURCE, type(error).__name__)
                raise TelegramError(f"{method}: {type(error).__name__}") from None
        body = response.json() if response.content else {}
        if response.status_code != 200 or not body.get("ok"):
            description = body.get("description", "") if isinstance(body, dict) else ""
            if "message is not modified" in str(description):
                return {}  # текст тот же — править нечего
            detail = f"{method}: HTTP {response.status_code} {description}".strip()
            mark_error(SOURCE, detail)
            raise TelegramError(detail)
        mark_ok(SOURCE)
        result = body["result"]
        if isinstance(result, list):
            return {"items": result}
        return result if isinstance(result, dict) else {}


def _keyboard(buttons: Buttons) -> dict[str, object]:
    return {
        "inline_keyboard": [[{"text": label, "callback_data": data} for label, data in buttons]]
    }
