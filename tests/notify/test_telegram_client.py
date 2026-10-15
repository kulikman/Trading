import json

import httpx
import pytest

from notify.telegram.client import TelegramClient, TelegramError

TOKEN = "123:test-token"  # noqa: S105 — тестовое значение


def client(handler: httpx.MockTransport) -> TelegramClient:
    return TelegramClient(TOKEN, "42", transport=handler)


def test_send_returns_message_id() -> None:
    seen: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    assert client(httpx.MockTransport(reply)).send("привет") == 7
    assert seen[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert json.loads(seen[0].content) == {
        "chat_id": "42",
        "text": "привет",
        "disable_notification": False,
    }


def test_error_has_no_token() -> None:
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError) as error:
        client(httpx.MockTransport(reject)).send("x")
    assert "chat not found" in str(error.value)
    assert TOKEN not in str(error.value)

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(TelegramError) as down:
        client(httpx.MockTransport(broken)).send("x")
    assert TOKEN not in str(down.value)  # адрес с токеном не попадает в журнал


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert TelegramClient.from_env() is None  # бот не настроен — сообщения не отправляются
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert isinstance(TelegramClient.from_env(), TelegramClient)


def test_edit_and_not_modified_is_ok() -> None:
    seen: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        return httpx.Response(
            400, json={"ok": False, "description": "Bad Request: message is not modified"}
        )

    bot = client(httpx.MockTransport(reply))
    bot.edit(7, "новый текст")
    bot.edit(7, "новый текст")  # тот же текст — не ошибка
    assert seen[0].url.path == f"/bot{TOKEN}/editMessageText"
    assert json.loads(seen[0].content)["message_id"] == 7
