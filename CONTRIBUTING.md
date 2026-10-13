# Contributing

Полные правила — в [`CLAUDE.md`](CLAUDE.md). Кратко:

## Настройка

```bash
make setup             # uv sync + pre-commit install
make db-up             # Postgres 16 (+pgvector) и Redis
cp .env.example .env   # заполнить ключи локально, никогда не коммитить
```

## Цикл работы

- Одна задача из `TASKS.md` = одна ветка = один PR.
- Перед PR: `make lint test` зелёный.
- Conventional Commits, тема в нижнем регистре.
- Неподтверждённые поля API и идеи — в `OPEN_QUESTIONS.md`, не в код.
