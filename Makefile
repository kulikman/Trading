.PHONY: setup db-up db-down migrate lint format test run-scheduler run-bot run-api

-include .env

# Local docker default (same defaults as docker-compose.yml); .env or the shell can override.
LOCAL_DATABASE_URL = postgresql+psycopg://$(or $(POSTGRES_USER),earnings):$(or $(POSTGRES_PASSWORD),earnings)@localhost:$(or $(POSTGRES_PORT),5432)/$(or $(POSTGRES_DB),earnings)
DATABASE_URL := $(or $(DATABASE_URL),$(LOCAL_DATABASE_URL))
export DATABASE_URL

setup:
	uv sync
	@if git config --get core.hooksPath >/dev/null; then \
		echo "WARNING: core.hooksPath=$$(git config --get core.hooksPath) is set, pre-commit hooks NOT installed."; \
		echo "Run: git config --unset core.hooksPath && make setup"; \
	else \
		uv run pre-commit install; \
	fi

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

migrate:
	uv run alembic upgrade head

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

run-scheduler:
	@echo "run-scheduler: available after T09 (scheduler)"; exit 1

run-bot:
	@echo "run-bot: available after T18 (Telegram bot)"; exit 1

run-api:
	@echo "run-api: available after T19 (FastAPI)"; exit 1
