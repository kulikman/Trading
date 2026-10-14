# Changelog

## [Unreleased]

### Changed
- Репозиторий переведён с шаблона Next.js + Supabase на Python-монорепо по `SPEC.md`. Шаблон доступен в истории git (коммит `fe4f9af`).

### Fixed
- Календарь Finnhub: ответ ограничен 1500 строками и теряет ранние даты — окно запрашивается кусками по 7 дней, кусок на пределе делится (найдено на первом живом прогоне: терялись 13 компаний вселенной). Фикстуры Finnhub перезаписаны реальными ответами.
- Ключи из `.env` (Finnhub, Alpha Vantage, Massive и др.) не передавались процессам `make` — планировщик не смог бы запустить календарь.
- Итоговая запись лога «Календаря» падала (`created` — зарезервированное поле `LogRecord`); добавлена проверка всех ключей `extra=` в коде. `make run-calendar` — разовый прогон.

### Added
- T09: планировщик (`core/scheduler/`, APScheduler 3.11, хранилище задач в Postgres): ежедневный запуск «Календаря» 06:00 ET и диспетчер задач события каждые 30 с; расписание задач события по SPEC §8 в `config/schedule.yaml` с переносом выходных и праздников, учётом AMC и сокращённых сессий. Агент «Календарь» (`agents/calendar/`): события вселенной на 21 день вперёд из Finnhub, сверка даты с Alpha Vantage (`confirmed` / `projected`), расхождение — `DATA_CALENDAR` в журнал, лог и сообщение «СИСТЕМА»; перенос даты обновляет событие и пишется в журнал `event_change`. Таблицы `event_job`, `event_change`, `apscheduler_jobs`, поле `event.fiscal_period` (миграция 0004); `make run-scheduler`.
- T08: `BrokerAdapter` и общая проверка ордера (только основная сессия, без рыночных ордеров в первые 5 минут, кроме стоп-гэпа); `ManualBroker` (инструкция для карточки, идемпотентность, подтверждение исполнения, позиции); заглушки IB и Freedom; `CostModel` (комиссия, половина спреда, проскальзывание на открытии) с параметрами брокера в `config/broker.yaml`.
- T07: адаптеры SEC EDGAR (подачи 8-K / 10-Q / 10-K, пресс-релизы 8-K п. 2.02, XBRL companyfacts) и квартальные финансы с выводом Q4 и нарастающих итогов, таблица `financial_quarter` (миграция 0003); FRED (VIXCLS, DGS10); обёртка Claude API со структурированным выводом, одним повтором, `DataError` и запретом секретов в запросе.
- T06: замена Benzinga — адаптеры Finnhub (календарь, история EPS) и Alpha Vantage (календарь, пересмотры консенсуса, история EPS), новости Massive; ежедневный снимок консенсуса (агент «Консенсус»), таблица `news_article` (миграция 0002); ключи в параметрах запроса маскируются; ответы-заглушки Alpha Vantage не кэшируются. SPEC §6, TASKS T06/T09/T11, DASHBOARD обновлены.
- T05: адаптер Massive (`adapters/massive/`) — свечи, NBBO, снимок акции, справочник опционов, снимок цепочки (IV, греки, OI); `implied_move` по ATM-стрэддлу; общий HTTP-клиент с повторами и кэшем Redis (`adapters/http.py`, `adapters/cache.py`), `DataError`; `config/sources.yaml`; Redis в CI.
- T04: `core/session_guard.py` — календарь NYSE (`pandas_market_calendars`): торговые дни, основная сессия с учётом сокращённых дней, следующее открытие, ET / МСК, недельная экспирация; `make test` проверяет покрытие (`core/` ≥ 85%, `session_guard` 100%).
- `DASHBOARD.md` — ТЗ на веб-дашборд; T19 в `TASKS.md` разбита на T19a (API) и T19b (`web/`); задачи T06, T07, T09, T16, T17, T18 дополнены данными для дашборда.
- T03: схема БД — 14 таблиц SPEC §5 (SQLAlchemy 2 + первая миграция Alembic), pydantic-модели домена в `core/domain/`, CHECK-ограничения из единых перечислений, `make migrate`, Postgres в CI.
- T02: `config/universe.yaml` (50 компаний, 11 секторов, 16 связей-информаторов), `thresholds.yaml` (SPEC §7, §9, §10, §17 + капитал $100 000, риск по Келли, без лимитов кластера и сезона), `registry.yaml`; загрузчик `core.config` со строгой валидацией.
- T01: каркас репозитория — `pyproject.toml` (uv, ruff, mypy, pytest), `Makefile`, `docker-compose.yml` (Postgres 16 + pgvector, Redis), pre-commit, CI.
