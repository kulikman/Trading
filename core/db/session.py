"""Подключение к Postgres. Адрес — только из переменной окружения DATABASE_URL."""

import os

from sqlalchemy import Engine, create_engine

from core.config import ConfigError


def database_url() -> str:
    """DATABASE_URL из окружения; `make` подставляет локальный адрес из docker-compose."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ConfigError("DATABASE_URL is not set: run `make db-up` and use `make migrate/test`")
    return url


def create_db_engine(url: str | None = None) -> Engine:
    """Engine с проверкой соединения перед выдачей из пула."""
    return create_engine(url or database_url(), pool_pre_ping=True)
