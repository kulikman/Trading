"""Тесты БД идут на настоящем Postgres (make db-up) в отдельной базе <имя>_test."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from core.config import ConfigError
from core.db.session import create_db_engine, database_url

REPO_ROOT = Path(__file__).resolve().parents[3]


def _base_url() -> URL:
    try:
        return make_url(database_url())
    except ConfigError as exc:
        message = f"{exc}. Database tests need Postgres: `make db-up && make test`."
        raise pytest.fail.Exception(message) from exc


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    base = _base_url()
    test_url = base.set(database=f"{base.database}_test")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    name = test_url.database
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    yield test_url.render_as_string(hide_password=False)
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = test_database_url
    return config


@pytest.fixture(scope="session")
def engine(alembic_config: Config, test_database_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_db_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Каждый тест — в транзакции, которая откатывается."""
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield db
        db.close()
        transaction.rollback()
