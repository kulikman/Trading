.PHONY: setup db-up db-down migrate lint format test run-scheduler run-calendar load-options build-archive backtest-data run-bot run-api

-include .env

# Local docker default (same defaults as docker-compose.yml); .env or the shell can override.
LOCAL_DATABASE_URL = postgresql+psycopg://$(or $(POSTGRES_USER),earnings):$(or $(POSTGRES_PASSWORD),earnings)@localhost:$(or $(POSTGRES_PORT),5432)/$(or $(POSTGRES_DB),earnings)
DATABASE_URL := $(or $(DATABASE_URL),$(LOCAL_DATABASE_URL))
export DATABASE_URL
REDIS_URL := $(or $(REDIS_URL),redis://localhost:$(or $(REDIS_PORT),6379)/0)
export REDIS_URL
# Ключи и контакты из .env — в окружение процессов (без export make их не передаёт).
export MASSIVE_API_KEY FINNHUB_API_KEY ALPHAVANTAGE_API_KEY SEC_USER_AGENT FRED_API_KEY ANTHROPIC_API_KEY

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
	uv run pytest --cov --cov-report=
	@# SPEC §13: core/ ≥ 85%; TASKS T04: session_guard 100%.
	uv run coverage report --include='core/*' --fail-under=85 --skip-covered --show-missing
	uv run coverage report --include=core/session_guard.py --fail-under=100 --show-missing

run-scheduler:
	uv run python -m core.scheduler

run-calendar:  ## разовый прогон «Календаря» (то же, что в 06:00 ET)
	uv run python -m agents.calendar

load-options:  ## архив опционов по прошлым отчётам: make load-options ARGS="--ticker NFLX" или ARGS="--all"
	uv run python -m backtest.load_option_history $(ARGS)

build-archive:  ## архив прошлых отчётов + отчёт о покрытии: make build-archive ARGS="--all"
	uv run python -m backtest.build_archive $(ARGS)

backtest-data:  ## данные выхода сделок бэктеста (минутные цены, iron condor): make backtest-data ARGS="--all"
	uv run python -m backtest.load_exit_data $(ARGS)

run-bot:
	@echo "run-bot: available after T18 (Telegram bot)"; exit 1

run-api:
	@echo "run-api: available after T19 (FastAPI)"; exit 1
