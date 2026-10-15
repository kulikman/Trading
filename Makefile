.PHONY: setup db-up db-down migrate lint format test run-scheduler run-calendar run-consensus load-options build-archive backtest-data backtest run-archive-daily promote run-bot run-api run-web rerun-job models-init deploy deploy-status cash learn-season server-learn-season server-promote

-include .env

# Local docker default (same defaults as docker-compose.yml); .env or the shell can override.
LOCAL_DATABASE_URL = postgresql+psycopg://$(or $(POSTGRES_USER),earnings):$(or $(POSTGRES_PASSWORD),earnings)@localhost:$(or $(POSTGRES_PORT),5432)/$(or $(POSTGRES_DB),earnings)
DATABASE_URL := $(or $(DATABASE_URL),$(LOCAL_DATABASE_URL))
export DATABASE_URL
REDIS_URL := $(or $(REDIS_URL),redis://localhost:$(or $(REDIS_PORT),6379)/0)
export REDIS_URL
# Ключи и контакты из .env — в окружение процессов (без export make их не передаёт).
export MASSIVE_API_KEY FINNHUB_API_KEY ALPHAVANTAGE_API_KEY SEC_USER_AGENT FRED_API_KEY ANTHROPIC_API_KEY DASHBOARD_API_TOKEN TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID

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

run-consensus:  ## разовый снимок консенсуса (то же, что в 06:10 ET)
	uv run python -m agents.consensus

load-options:  ## архив опционов по прошлым отчётам: make load-options ARGS="--ticker NFLX" или ARGS="--all"
	uv run python -m backtest.load_option_history $(ARGS)

build-archive:  ## архив прошлых отчётов + отчёт о покрытии: make build-archive ARGS="--all"
	uv run python -m backtest.build_archive $(ARGS)

backtest-data:  ## данные выхода сделок бэктеста (минутные цены, iron condor): make backtest-data ARGS="--all"
	uv run python -m backtest.load_exit_data $(ARGS)

backtest:  ## бэктест стратегий на move_ratio → reports/backtest_<дата>.md
	uv run python -m backtest.run

run-archive-daily:  ## разовое пополнение архива свежими отчётами (то же, что в 18:30 ET)
	uv run python -m backtest.daily_archive

rerun-job:  ## повторить упавшую задачу события: make rerun-job ARGS="NFLX T-7 options"
	uv run python -m core.scheduler.rerun $(ARGS)

models-init:  ## стартовая версия моделей p_beat, p_up, move_ratio (SPEC §9; повтор ничего не меняет)
	uv run python -m models

promote:  ## поднять плагин на ступень: make promote ARGS="mode_c" (отказ — с причиной)
	uv run python -m core.registry promote $(ARGS)

run-bot:
	@echo "run-bot: available after T18 (Telegram bot)"; exit 1

learn-season:  ## обучение сезона (SPEC §9): версия моделей, θ и Келли, карантин; отчёт reports/season_*.md
	uv run python -m learning.season

server-learn-season:  ## обучение сезона на сервере (контейнер планировщика); отчёт — ~/trading-reports на сервере
	ssh $(DEPLOY_HOST) 'docker exec trading-scheduler python -m learning.season'

server-promote:  ## promote на сервере: make server-promote ARGS="mode_c"
	ssh $(DEPLOY_HOST) 'docker exec trading-scheduler python -m core.registry promote $(ARGS)'

cash:  ## счёт Real: make cash ARGS="deposit 10000 комментарий" / ARGS="withdraw 2000"
	uv run python -m execution.cash $(ARGS)

run-api:  ## API дашборда на http://127.0.0.1:8000 (нужен DASHBOARD_API_TOKEN в .env)
	uv run python -m api

run-web:  ## сайт дашборда на http://127.0.0.1:3000 (сначала make run-api)
	cd web && pnpm install --frozen-lockfile && pnpm dev --hostname 127.0.0.1  # не в локальную сеть: на экране баланс

# --- Сервер (E9): Hetzner рядом с signals.aurioncode.com, сайт — trading.aurioncode.com ---
DEPLOY_HOST ?= brain-hetzner
DEPLOY_PATH ?= trading
DEPLOY_COMPOSE = docker compose --env-file $$HOME/.config/trading/env -f deploy/compose.yml

deploy:  ## выкатить закоммиченный код на сервер и пересобрать контейнеры (данные и секреты не едут)
	@test -z "$$(git status --porcelain)" || (echo "есть незакоммиченные изменения — сначала commit"; exit 1)
	git ls-files -z | rsync -a --from0 --files-from=- ./ $(DEPLOY_HOST):$(DEPLOY_PATH)/
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) up -d --build --remove-orphans'

deploy-status:  ## контейнеры на сервере и последние строки планировщика
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) ps && docker logs --tail 20 trading-scheduler'
