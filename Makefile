.PHONY: setup db-up db-down migrate lint format test run-scheduler run-bot run-api

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
	@echo "migrate: available after T03 (Alembic schema)"; exit 1

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
