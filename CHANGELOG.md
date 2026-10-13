# Changelog

## [Unreleased]

### Changed
- Репозиторий переведён с шаблона Next.js + Supabase на Python-монорепо по `SPEC.md`. Шаблон доступен в истории git (коммит `fe4f9af`).

### Added
- T02: `config/universe.yaml` (50 компаний, 11 секторов, 16 связей-информаторов), `thresholds.yaml` (SPEC §7, §9, §10, §17 + капитал $100 000, риск по Келли, без лимитов кластера и сезона), `registry.yaml`; загрузчик `core.config` со строгой валидацией.
- T01: каркас репозитория — `pyproject.toml` (uv, ruff, mypy, pytest), `Makefile`, `docker-compose.yml` (Postgres 16 + pgvector, Redis), pre-commit, CI.
