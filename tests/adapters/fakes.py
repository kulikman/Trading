"""Фейковый HTTP-сервер для контрактных тестов адаптеров."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

Body = dict[str, Any] | list[Any] | str
Route = Callable[[httpx.Request], Body | tuple[int, Body]]


def load_json(source: str, name: str) -> Any:
    return json.loads((FIXTURES / source / name).read_text(encoding="utf-8"))


def load_text(source: str, name: str) -> str:
    return (FIXTURES / source / name).read_text(encoding="utf-8")


class FakeApi:
    """Отдаёт ответ маршрута по пути запроса; str — как текст (CSV), остальное — как JSON."""

    def __init__(self, routes: dict[str, Route]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"error": "not found"})
        result = route(request)
        status, body = result if isinstance(result, tuple) else (200, result)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)
