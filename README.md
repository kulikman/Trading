# Trading Earnings Engine

Сервис, который готовит, принимает и сопровождает сделки вокруг квартальных отчётов компаний США.

- Что строим — [`SPEC.md`](SPEC.md)
- Порядок работ — [`TASKS.md`](TASKS.md)
- Правила для разработчиков и AI-агентов — [`CLAUDE.md`](CLAUDE.md)
- Неподтверждённое и открытые вопросы — [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md)

**Стек:** Python 3.12 (uv) · FastAPI · PostgreSQL 16 + pgvector · Redis · APScheduler · scikit-learn · aiogram 3 · Next.js (только `web/`, чтение).

## Быстрый старт

Нужны: [uv](https://docs.astral.sh/uv/), Docker, make.

```bash
make setup      # зависимости + pre-commit хуки
make db-up      # Postgres + Redis в docker
make lint test  # ruff + mypy + pytest
```

Секреты — только в `.env` (шаблон — `.env.example`, без значений). `.env` в git не попадает.

## Лицензия

Private — All rights reserved.
