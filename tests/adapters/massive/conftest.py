import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from adapters.massive.client import MassiveClient
from core.config import load_config
from core.config.sources import MassiveSettings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "massive"
API_KEY = "test-massive-key"


def fixture(name: str) -> dict[str, Any]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


class FakeMassive:
    """Отдаёт фикстуры по пути запроса и запоминает запросы."""

    def __init__(self, routes: dict[str, Callable[[httpx.Request], dict[str, Any]]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"status": "NOT_FOUND"})
        return httpx.Response(200, json=route(request))


@pytest.fixture
def settings() -> MassiveSettings:
    return load_config().sources.massive


def make_client(settings: MassiveSettings, fake: FakeMassive) -> MassiveClient:
    return MassiveClient.create(settings, API_KEY, transport=httpx.MockTransport(fake))
