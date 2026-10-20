# Earnings Engine — техническое задание

Версия 1.0 · 13.10.2026 · Заказчик: Антон Куликов

Комплект для Claude Code: `CLAUDE.md` (правила работы), `SPEC.md` (что строим — этот файл), `TASKS.md` (порядок работ с промптами и приёмкой). Все три лежат в корне репозитория.

---

## 1. Что строим

Сервис, который готовит, принимает и сопровождает сделки вокруг квартальных отчётов компаний США.

Цепочка: календарь отчётов → профиль сектора и компании → три вероятностные модели → сравнение с ценой рынка (опционы, Polymarket) → решение (вход / пропуск с причиной) → карточка сделки в Telegram → сопровождение до закрытия → запись итога для обучения.

**Главные правила, которые нельзя нарушать:**

1. Ордера только в основную сессию NYSE, 9:30–16:00 ET. Пре-маркет и after-hours — только анализ.
2. Первые 5 минут после открытия — без рыночных ордеров (исключение — стоп-гэп).
3. По каждому состоявшемуся отчёту из календаря есть запись `Decision`. Тихих событий нет.
4. LLM не считает вероятности и не принимает решений. LLM превращает текст в числовые признаки и пишет человеческие резюме. Вероятности считают обученные модели, решения — детерминированные правила.
5. Веса моделей меняются только процедурой обучения (раздел 9), никогда вручную.
6. Новые агенты и стратегии подключаются через реестр, без изменения ядра (раздел 7).
7. В MVP исполнение ручное: система присылает карточку, человек ставит ордера у брокера и жмёт «Исполнено».

---

## 2. Объём MVP и что вне его

**В MVP (фазы 0–3, раздел 14):**
- вселенная 66 компаний (постоянное ядро) + до ~54 динамических из watchlist при наличии отчёта на неделе, ликвидные опционы, 16 секторов;
- агенты данных: Календарь, Сектор, Досье, Консенсус, Позиционирование, Макро, Опционы, Polymarket;
- три модели (`p_beat`, `p_up`, `move_ratio`) на логистической регрессии + калибровка;
- режимы входа A, B, C; конструкции: акция, акция + коллар, вертикальный спред, стрэддл, iron condor, Polymarket, «нет сделки»;
- журнал решений с кодами пропуска и теневыми сделками;
- Telegram-бот: карточки, кнопки, дайджесты, сторож;
- Paper Trading всех решений;
- веб-интерфейс только на чтение: сектора → компании → профиль → журнал.

**Вне MVP:**
- автоматическое исполнение через API брокера (фаза 5);
- градиентный бустинг (после 300+ событий);
- секторные поправки весов (с 3–4 сезона).

---

## 3. Стек

| Слой | Технология | Примечание |
|---|---|---|
| Язык | Python 3.12 | типизация везде, `mypy --strict` на `core/` |
| API и веб-бэкенд | FastAPI | |
| БД | PostgreSQL 16 (+ pgvector) | миграции — Alembic |
| Кэш, блокировки | Redis | |
| Планировщик | APScheduler с хранилищем задач в Postgres | календарь биржи — `pandas_market_calendars` (праздники, сокращённые дни) |
| Модели | scikit-learn | позже LightGBM |
| LLM | Claude API | только структурированный вывод по JSON-схеме |
| Telegram | aiogram 3 | |
| Данные рынка | Massive (Python-клиент) | |
| Архив для бэктеста | Massive: дневные цены опционных контрактов за 2 года, IV и греки — пересчёт по Блэку–Шоулзу; IVolatility API (Backtest Plus) — только если 2 лет мало (решение после бэктеста T12) | фаза 1 |
| Брокер | интерфейс `BrokerAdapter`; реализации IB и Freedom (Tradernet) — фаза 5 | в MVP — заглушка `ManualBroker` |
| Интерфейс | Next.js | только чтение в MVP |
| Конфигурация | `.env` + `config/*.yaml` | секреты только в env |
| Тесты | pytest, pytest-asyncio, freezegun | |

---

## 4. Структура репозитория

```
earnings-engine/
├── SPEC.md
├── CLAUDE.md
├── config/
│   ├── universe.yaml          # компании, сектора, граф информаторов
│   ├── thresholds.yaml        # пороги, лимиты риска, параметры режимов
│   └── registry.yaml          # включённые агенты и стратегии + статус
├── core/
│   ├── domain/                # pydantic-модели сущностей
│   ├── db/                    # SQLAlchemy, миграции Alembic
│   ├── scheduler/             # задачи T−21…T+20, привязка к календарю биржи
│   ├── registry/              # загрузка и жизненный цикл плагинов
│   ├── state_machine/         # машина состояний TradeCard
│   └── session_guard.py       # проверка «основная сессия открыта»
├── adapters/
│   ├── massive/               # котировки, цепочки опционов, новости, история цен опционов
│   ├── finnhub/               # календарь отчётов, консенсус, факт
│   ├── alphavantage/          # второй источник даты, пересмотры консенсуса, история EPS
│   ├── ivolatility/           # резерв: архив глубже 2 лет, если понадобится (T12)
│   ├── edgar/                 # 10-Q, 10-K, 8-K
│   ├── fred/
│   ├── polymarket/
│   ├── llm/                   # обёртка Claude API со схемами
│   └── broker/                # BrokerAdapter, ManualBroker, (ib/, freedom/ — фаза 5)
├── agents/                    # плагины-агенты, каждый в своей папке
├── strategies/                # плагины-стратегии
├── models/                    # обучение, калибровка, инференс
├── decision/                  # Chief Trader, Capital Manager, правила
├── execution/                 # исполнитель, сопровождение, P&L
├── notify/telegram/           # бот, шаблоны карточек, сторож
├── learning/                  # журнал, теневые сделки, отчёт сезона
├── backtest/                  # прогон на архиве
├── api/                       # FastAPI для интерфейса
├── web/                       # Next.js
└── tests/
```

---

## 5. Модель данных

DDL ниже — ориентир, не финальная схема. Все таблицы с `created_at`, `updated_at`. Все версии резюме и прогнозов хранятся, не перезаписываются.

```sql
CREATE TABLE sector (
  id TEXT PRIMARY KEY,                 -- 'banks', 'semis'
  name TEXT NOT NULL,
  key_metrics JSONB NOT NULL,          -- ['FICC','IB fees',...]
  macro_sensitivity JSONB,
  data_sources JSONB
);

CREATE TABLE sector_summary (
  id BIGSERIAL PRIMARY KEY,
  sector_id TEXT REFERENCES sector,
  as_of DATE NOT NULL,
  trend SMALLINT CHECK (trend IN (-1,0,1)),
  confidence REAL,
  peer_surprise_mean REAL,
  sector_momentum_30d REAL,
  facts JSONB, risks JSONB,
  text_summary TEXT                    -- для человека
);

CREATE TABLE peer_edge (               -- граф «кто кому сигналит»
  from_ticker TEXT, to_ticker TEXT,
  strength REAL, lag_days INT,
  PRIMARY KEY (from_ticker, to_ticker)
);

CREATE TABLE company (
  ticker TEXT PRIMARY KEY,
  sector_id TEXT REFERENCES sector,
  name TEXT, overview TEXT,
  segments JSONB, risks JSONB,
  options_liquid BOOLEAN,
  calibration_status TEXT CHECK (calibration_status IN ('active','quarantine')) DEFAULT 'active'
);

CREATE TABLE report_audit (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT REFERENCES company,
  fiscal_period TEXT, report_date DATE,
  segments_expected JSONB, segments_actual JSONB,
  guidance JSONB, management_tone REAL,
  named_risks JSONB, summary TEXT,
  source_urls JSONB
);

CREATE TABLE earnings_track (          -- одна строка на отчёт
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT REFERENCES company,
  report_date DATE, report_time TEXT CHECK (report_time IN ('BMO','AMC','DURING')),
  eps_consensus REAL, eps_actual REAL, eps_surprise_pct REAL,
  rev_consensus REAL, rev_actual REAL, rev_surprise_pct REAL,
  guidance_change SMALLINT,            -- -1/0/1
  implied_move REAL, actual_move REAL, move_ratio REAL,
  reaction_cause TEXT,                 -- обязательно, пишет Досье на T+1
  model_p_beat REAL, model_p_up REAL, model_move_ratio REAL,
  decision TEXT, skip_reasons TEXT[], shadow_pnl REAL
);

CREATE TABLE consensus_snapshot (      -- свой архив пересмотров: бесплатные источники дают только текущую оценку
  ticker TEXT, fiscal_period TEXT, as_of DATE,
  eps_estimate REAL, rev_estimate REAL,
  PRIMARY KEY (ticker, fiscal_period, as_of)
);

CREATE TABLE event (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT REFERENCES company,
  report_date DATE, report_time TEXT,
  date_status TEXT,                    -- projected / confirmed
  date_sources JSONB,                  -- минимум 2 источника
  queue_status TEXT,                   -- planned / profiling / signals / decided / done
  UNIQUE (ticker, report_date)
);

CREATE TABLE feature_snapshot (
  event_id BIGINT REFERENCES event,
  stage TEXT CHECK (stage IN ('T-7','T-3','T-1','T0')),
  agent_id TEXT, agent_version TEXT,
  features JSONB,                      -- только числа
  PRIMARY KEY (event_id, stage, agent_id)
);

CREATE TABLE forecast (
  event_id BIGINT REFERENCES event,
  stage TEXT, model_version TEXT,
  p_beat REAL, p_up REAL, move_ratio REAL,
  market_p_beat REAL, market_p_up REAL, implied_move REAL,
  edge_beat REAL, edge_up REAL, edge_move REAL,
  PRIMARY KEY (event_id, stage)
);

CREATE TABLE decision (
  id BIGSERIAL PRIMARY KEY,
  event_id BIGINT REFERENCES event UNIQUE,
  status TEXT CHECK (status IN ('ENTERED','SKIPPED','CANCELLED','DATA_FAIL')),
  reasons TEXT[],                      -- коды из раздела 10, первый — главный
  mode TEXT, strategy_id TEXT, construct TEXT,
  shadow JSONB,                        -- теневая сделка для пропусков
  decided_at TIMESTAMPTZ
);

CREATE TABLE trade_card (
  id BIGSERIAL PRIMARY KEY,
  decision_id BIGINT REFERENCES decision,
  state TEXT,                          -- раздел 11
  paper BOOLEAN NOT NULL DEFAULT TRUE,
  legs JSONB,                          -- инструмент, кол-во, лимит, сторона
  stop JSONB, trailing JSONB,
  fills JSONB,
  tg_message_id BIGINT,
  pnl_total REAL, pnl_direction REAL, pnl_vol REAL, pnl_ivcrush REAL
);

CREATE TABLE trade_card_transition (
  card_id BIGINT REFERENCES trade_card,
  at TIMESTAMPTZ, from_state TEXT, to_state TEXT,
  reason TEXT, payload JSONB
);

CREATE TABLE plugin (
  id TEXT, version TEXT, kind TEXT CHECK (kind IN ('agent','strategy')),
  stage TEXT CHECK (stage IN ('shadow','paper','live_small','live')),
  weight REAL, enabled BOOLEAN,
  PRIMARY KEY (id, version)
);
```

---

## 6. Адаптеры источников

Каждый адаптер реализует интерфейс, кэширует ответы в Redis и пишет сырой ответ в лог для отладки. Таймауты, ретраи с backoff, явные ошибки `DataError(source, detail)`.

| Адаптер | Что даёт | Эндпоинты / заметки |
|---|---|---|
| `massive.market` | цены, свечи, снапшоты, websocket | aggregates, snapshot, websocket |
| `massive.options` | цепочки, IV, греки, OI | options contracts, snapshot-chain |
| `massive.news` | новости компании | `/v2/reference/news` — входит в тариф Stocks |
| `finnhub` | календарь отчётов (основной), консенсус EPS и выручки, факт, сюрприз | `/calendar/earnings` (`date`, `hour`, `epsEstimate`, `revenueEstimate`, `epsActual`, `revenueActual`, `quarter`, `year`), `/stock/earnings` (`actual`, `estimate`, `surprise`, `surprisePercent`, `period`); бесплатный тариф |
| `alphavantage` | второй источник даты отчёта, пересмотры и разброс консенсуса, история EPS | `EARNINGS_CALENDAR` (CSV), `EARNINGS_ESTIMATES` (среднее, максимум, минимум, число аналитиков, оценка 7/30/60/90 дней назад), `EARNINGS` (EPS с 1996 г.); бесплатно 25 запросов в день |
| `massive.history` | дневные цены опционных контрактов, в том числе истёкших, за последние 2 года (по наблюдению — скользящее окно); ~5 запросов в минуту (по наблюдению) | `/v3/reference/options/contracts` (`as_of`), `/v2/aggs` по контракту; только `backtest/` и архив `option_daily_bar` |
| `ivolatility` | архив IV, IVX, поверхности глубже 2 лет | резерв: подключается по решению после бэктеста T12 |
| `edgar` | 10-Q, 10-K, 8-K (пресс-релиз отчёта) | |
| `fred` | ставки, доходности, VIX (`VIXCLS`) | |
| `polymarket` | цена и ликвидность рынков на beat | правила расчёта рынка сохранять в `event` |
| `llm` | Claude API | вход — текст, выход — объект по JSON-схеме; невалидный ответ = ретрай 1 раз, потом `DATA_FAIL` |
| `broker` | `BrokerAdapter` | см. ниже |

**Замена Benzinga (решение заказчика 13.10.2026):** вместо Benzinga ($99) — бесплатные Finnhub и Alpha Vantage, новости — Massive. Guidance в готовом виде бесплатно нет — извлекается LLM из пресс-релиза 8-K (агент «Досье»). Лицензии бесплатных тарифов — только личное некоммерческое использование.

**BMO/AMC:** Finnhub `hour`: `bmo` → BMO, `amc` → AMC, `dmh` → DURING. Alpha Vantage `timeOfTheDay`: `pre-market` → BMO, `post-market` → AMC; у ~77% строк календаря AV время пустое, поэтому основной источник — Finnhub. Нет данных — время неизвестно (не угадываем).

**Дата отчёта:** событие получает `date_status = confirmed` только при совпадении дат Finnhub и Alpha Vantage. Флага «подтверждено» нет ни у одного бесплатного источника — его роль играет правило двух источников. Расхождение → пуш «СИСТЕМА» и `DATA_CALENDAR`.

**EPS:** факт Finnhub — non-GAAP, EDGAR — GAAP; в расчёте сюрприза не смешивать.

**Сверка цены:** перед выдачей сигнала цена из Massive сверяется с котировкой брокера (в MVP — с последним снапшотом). Расхождение > 0,3% → `DATA_MISMATCH`, сигнал не выдаётся.

```python
class BrokerAdapter(Protocol):
    def quote(self, symbol: str) -> Quote: ...
    def place(self, order: Order) -> OrderId: ...          # всегда outside_rth=False
    def cancel(self, order_id: OrderId) -> None: ...
    def positions(self) -> list[Position]: ...
    def fills(self, since: datetime) -> list[Fill]: ...
```

`ManualBroker.place()` ничего не отправляет, а возвращает инструкцию для карточки; исполнение подтверждается кнопкой в Telegram.

---

## 7. Плагины: агенты и стратегии

Агенты и стратегии — плагины в `agents/<id>/` и `strategies/<id>/`, регистрируются в `config/registry.yaml`. Ядро не знает их имён.

```python
class Agent(Protocol):
    id: str
    version: str
    triggers: list[Trigger]          # расписание (T-14, T-7…) или событие
    reads: list[str]                 # какие данные нужны
    output_schema: type[BaseModel]   # только числовые поля + опц. текст для человека
    def run(self, ctx: EventContext) -> BaseModel: ...

class Strategy(Protocol):
    id: str
    version: str
    mode: str                        # 'A' | 'B' | 'C' | новый
    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip: ...
    def exit_rules(self, card: TradeCard, market: MarketState) -> list[Action]: ...
```

**Жизненный цикл плагина** (`plugin.stage`):
`shadow` (считает, ни на что не влияет) → `paper` (теневые сделки) → `live_small` (вес 5%) → `live`.
Переход вверх — только командой `promote`, которая проверяет: на отложенной выборке Brier улучшился (агент) или Sharpe улучшился (стратегия), и наблюдений ≥ 30. Иначе команда отказывает с причиной.

**Защита от перегрузки:** отчёт сезона считает вклад каждого агента (модель с ним и без него). Агент без прироста помечается к отключению. Признаки с корреляцией > 0,8 помечаются к объединению. Бюджет активных признаков задаётся в `thresholds.yaml` (старт — 12).

---

## 8. Агенты MVP и расписание

| Агент | Когда | Выход (числовые признаки) |
|---|---|---|
| Календарь | ежедневно 06:00 ET; новые события на T−21 | `event` с двумя источниками даты, порядок после информаторов |
| Сектор | раз в 2 недели в сезон, раз в месяц вне его, после отчёта лидера сектора | `sector_summary`: `trend`, `confidence`, `peer_surprise_mean`, `sector_momentum_30d` |
| Досье | скелет один раз; обновление T−10; итог T+1 | `report_audit`, строка `earnings_track` с `reaction_cause` |
| Консенсус | ежедневно в сезон (снимок в `consensus_snapshot`); признаки T−10, T−3 | `revision_trend_7_90`, `estimate_dispersion` |
| Позиционирование | T−7, T−3, T−1 | `pre_run_30d`, `pre_run_3d`, `short_interest_days`, `volume_anomaly` |
| Макро | ежедневно | `vix`, `us10y`, `regime` |
| Опционы | T−7, T−3, T−1 15:00 ET | `implied_move`, `skew_25d`, `term_slope`, `iv_rank` |
| Polymarket | T−3, T−1 | `pm_p_beat`, `pm_liquidity` |

**Расписание события** (BMO; для AMC всё со дня T0 сдвигается на день):

| Момент | Задача |
|---|---|
| T−21 | подтверждение даты, постановка в очередь |
| T−14 | цикл Сектора |
| T−10 | Досье + Консенсус |
| T−7 | Позиционирование, Опционы → прогноз → решение режима A |
| T−3 | Сектор (информаторы), Опционы, Polymarket → прогноз → ворота режима B |
| T−1 15:00 | финальный прогноз, выход A, решение B |
| T−1 15:30–15:55 | окно входа B |
| T−1 16:30 | вечерний дайджест + план |
| T0 ~07:30 | парсинг отчёта (Finnhub + 8-K), сюрприз, guidance |
| T0 09:00 | пуш «Быть у терминала» |
| T0 09:30–09:35 | стоп-гэп |
| T0 10:00–10:30 | решение режима C; к 10:15 нет сигнала — нет входа |
| T0 до 11:00 | закрытие B и опционных конструкций |
| T+1 | итог в `earnings_track`, теневые сделки |
| T+1…T+20, 16:05 | трейлинг режима C |

Все задачи выполняются только в торговые дни по `pandas_market_calendars`. Задача, попавшая на выходной или праздник, переносится на предыдущий торговый день (анализ) или следующий (исполнение) — правило в `scheduler/`.

---

## 9. Модели и обучение

Три модели, одна форма: `logit(p) = β0 + Σ βi·xi`, затем калибровка (Platt; изотоническая при 300+ наблюдениях).

| Модель | Цель | Рыночный эталон |
|---|---|---|
| `p_beat` | EPS ≥ консенсуса | `pm_p_beat` (если рынок есть) |
| `p_up` | цена закрытия T0 (AMC: T+1) > закрытия T−1 | 0,5 с поправкой на `skew_25d` |
| `move_ratio` | P(\|движение\| > `implied_move`) | 0,5 |

**Стартовые β для `p_up`** (только до первого обучения): `disclosure` +2,0 · `revision_trend` +1,5 · `peer_surprise` +1,2 · `sector_trend` +0,6 · `short_interest` +0,3 · `skew` −0,5 · `guidance_risk` −0,8 · `pre_run` −1,0.

**Преимущество:** `edge = p_model − p_market`. Сделка рассматривается при `edge > costs + 0.03` и уверенности ≥ θ режима.

**Обучение (команда `learn season`):**
1. Собрать все события сезона из `feature_snapshot`, `forecast`, `earnings_track`.
2. Разбить по времени: последние 25% — отложенная выборка.
3. Обучить три модели, откалибровать.
4. Принять новую версию, только если Brier на отложенной выборке улучшился. Иначе оставить старую.
5. Подобрать θ и долю Келли по максимуму Sharpe на истории, включая теневые сделки.
6. Сохранить версию модели с метриками; версия попадает в `forecast.model_version`.

**Правило 30:** любой вывод по сегменту (сектор, режим, конструкция) — только при ≥ 30 наблюдениях.
**Карантин:** Brier компании > 0,30 на ≥ 6 отчётах → `calibration_status = quarantine`, для неё разрешён только режим C.

**Период сбора данных (сезоны 1–2):** все решения в Paper; θ = 0,50 для paper-слоя; 20% событий оцениваются с отклонёнными весами (Thompson sampling) — помечать флагом `exploration` в `forecast`.

---

## 10. Решение

**Chief Trader** перебирает включённые стратегии, собирает предложения, **Capital Manager** режет размер и лимиты, **Black Swan** может наложить вето. Если ни одно предложение не прошло — `Decision.status = SKIPPED` с кодами.

**Размер позиции:** `min(¼ Kelly, risk_budget / (2 × implied_move))`; в сезоны 1–2 — ⅛ Kelly.
`f = 0.25 · (p·b − (1−p)) / b`, где `b = W/L` (по истории конструкции).

**Режимы:**

| Режим | Вход | Условия | Стоп | Выход |
|---|---|---|---|---|
| A | T−7, лимит по закрытию T−8 | `pre_run_30d` < +10%, VIX < 25, `sector_trend` ≥ 0 | 1,5 × ATR(14) | T−1 15:50, обязательно |
| B | T−1 15:30–15:55 | все ворота: преимущество, уверенность ≥ θ_B, нет `PEER_CONFLICT`, нет `PRE_RUN`, компания не в карантине | стоп-гэп на открытии | 09:30 стоп / 10:00–10:30 переход в C / иначе до 11:00; максимум T+1 |
| C | T0 10:00–10:30, лимит ≤ VWAP первого часа + 0,3% | все четыре: сюрприз EPS и выручки > 5%, guidance в ту же сторону, цена в ту же сторону, объём > 2× среднего | трейлинг 2 × ATR(14), пересчёт 16:05 | стоп / закрытие ниже SMA(5) / T+20 |

**Рост перед отчётом (`pre_run_3d`):** < +3% — без изменений; +3…+6% — A нет, B × 0,5; > +6% без причины — `PRE_RUN`; > +6% с причиной (`disclosure` ≠ 0 или отчёт информатора) — B без изменений; ≤ −4% — A на отскок, B × 1,2 при бычьем сигнале.

**Конструкции по типу преимущества:**

| Преимущество | Конструкция | Выход |
|---|---|---|
| направление, через отчёт | акция + коллар (пут ≈ −5%, колл ≈ +7–8%) или вертикальный спред | по режиму B |
| `move_ratio` > 1,3 | стрэддл / стрэнгл, вход T−1 | до 11:00 T0; стоп −50% премии, цель +100% |
| `move_ratio` < 0,75 | iron condor, вход T−1 за час до закрытия | до 11:00 T0; стоп 2× премии, цель 50% |
| Polymarket недооценивает beat на ≥ 5 п.п. | бинарный контракт | до расчёта |
| подтверждённый сюрприз | акция, режим C | трейлинг |

Голые проданные опционы запрещены. Опционы не держатся до экспирации. Экспирация — ближайшая пятница после отчёта; если пятница — праздник, четверг (проверка по календарю биржи).

**Коды пропуска:** `EDGE_LOW`, `CONF_LOW`, `PRE_RUN`, `PEER_CONFLICT`, `IV_EXPENSIVE`, `LIQUIDITY`, `CLUSTER_LIMIT`, `CALIBRATION`, `MACRO_BLOCK`, `C_NOT_CONFIRMED`, `DATA_MASSIVE`, `DATA_BROKER`, `DATA_CALENDAR`, `DATA_MISMATCH`.

**Теневая сделка:** для каждого `SKIPPED` считается P&L, как если бы лучшая отклонённая конструкция была исполнена по тем же правилам.

**Риск-лимиты** (`thresholds.yaml`): риск на сделку; кластер (сектор × неделя) — одна ставка; суммарный открытый риск сезона; 5 убытков подряд → пауза 24 ч и только Paper; просадка модуля > 10% → ручной разбор, > 15% → только Paper; Black Swan жёлтый → × 0,7, оранжевый → только уверенность > 80% и × 0,4, красный → нет новых входов; спред опциона < 5% цены, акции < 0,1%.

---

## 11. Машина состояний карточки

```
PLANNED → ARMED → OPEN → [C_MODE] → CLOSING → CLOSED
            ↓        ↓
       CANCELLED   STOPPED
```

- Каждый переход пишется в `trade_card_transition` и порождает сообщение в Telegram.
- `ARMED → OPEN` только после подтверждения исполнения (кнопка или `broker.fills`). Нет подтверждения 15 минут — напоминание.
- Любой переход, требующий ордера, проверяется `session_guard`: вне 9:30–16:00 ET — отказ и лог.
- Переходы идемпотентны: повтор события не создаёт второго ордера.

---

## 12. Telegram

**Типы сообщений:** ДЕЙСТВИЕ (звук), БЫТЬ У ТЕРМИНАЛА (звук, за 30 мин), СОПРОВОЖДЕНИЕ (без звука, 16:05), ПРОПУСК (без звука), ДАЙДЖЕСТ (08:30 и 16:30 ET, без звука), СИСТЕМА (звук).

**Механика:** одна карточка = одно сообщение, редактируется при смене состояния; действие приходит ответом на него. Кнопки: «Исполнено» · «Не исполнил» · «Детали». Время всегда в ET и МСК (учитывать переход США на зимнее время).

**Сторож:** отдельный процесс на другом хосте. Знает расписание ожидаемых сообщений; если сообщение не ушло в течение 5 минут после срока — шлёт «СИСТЕМА МОЛЧИТ».

**Шаблон карточки (режим B):**

```
GS · ОТЧЁТ 13.10 до открытия · Режим B · 64%
ВХОД  12.10, 15:30–15:55 ET (22:30–22:55 МСК)
  Купить  GS             17 шт.  лимит ≤ 897.00
  Купить  PUT 850 16.10   1 шт.  лимит ≤ 6.50
  Продать CALL 960 16.10  1 шт.  лимит ≥ 5.80
  Стоп    870 (только основная сессия)
ДАЛЬШЕ
  13.10 9:00 — план на открытие
  9:30  ниже 870 → закрыть всё
        870–925 → закрыть до 11:00
        выше 925 → ждать сигнал 10:00–10:30
```

**Шаблон пропуска:**

```
MS · отчёт 14.10 до открытия · НЕ ВХОДИМ
Причина: PRE_RUN — +7,4% за 3 дня без триггера
Доп.: IV_EXPENSIVE — ±5,8% против ±4,1% в истории
Теневая сделка записана
```

Цифры в шаблонах условные.

---

## 13. Нефункциональные требования

- **Время:** всё хранится в UTC, показывается в ET и МСК. Никаких наивных `datetime`.
- **Идемпотентность:** каждая задача планировщика имеет ключ `(event_id, stage, job)`; повторный запуск не дублирует записи и сообщения.
- **Логи:** структурированные (JSON), с `event_id` и `card_id`.
- **Секреты:** только переменные окружения; ключи брокера никогда не попадают в логи и LLM.
- **LLM-вызовы:** всегда со схемой вывода; в промпт не передаются ключи, позиции и размер капитала.
- **Отказоустойчивость:** сбой любого адаптера → `DATA_*` в `decision`, пуш СИСТЕМА, сигнал не выдаётся. Система не «догадывается» при нехватке данных.
- **Тесты:** покрытие `core/`, `decision/`, `state_machine/` ≥ 85%. Обязательные тесты: `session_guard` (выходные, праздники, сокращённые дни, переход на зимнее время), правило экспирации, коды пропуска, идемпотентность переходов.

---

## 14. Этапы и критерии приёмки

| Фаза | Содержание | Приёмка |
|---|---|---|
| 0. Фундамент | репозиторий, БД и миграции, `universe.yaml` (66 компаний, 16 секторов, граф) + `watchlist.yaml` (54 тикера, динамически), адаптеры Massive (рынок, опционы, новости), Finnhub, Alpha Vantage, FRED, EDGAR; `session_guard`; планировщик с календарём биржи | `make test` зелёный; за неделю календарь собран для всей вселенной с подтверждёнными датами; расхождения дат видны в логе |
| 1. Архив и бэктест | наполнение `earnings_track` за 2 года (Massive — цены опционов, Alpha Vantage `EARNINGS`, Finnhub; глубже — IVolatility по решению после бэктеста); расчёт `implied_move`, `actual_move`, `move_ratio`; бэктест режима C и ставок на `move_ratio` с издержками | отчёт бэктеста: число событий, точность, EV после издержек, Sharpe по режимам и конструкциям |
| 2. Конвейер события | агенты MVP как плагины, реестр, три модели со стартовыми весами, решение, журнал с кодами пропуска, Telegram-бот, сторож, Paper Trading | один полный цикл T−21…T+20 на реальном отчёте; у каждого отчёта есть `Decision`; все пуши пришли вовремя |
| 3. Сезоны 1–2 | работа в Paper, исследование 20%, команда `learn season` | ~100 событий в журнале; новая версия весов принята или отклонена по Brier; отчёт вклада агентов |
| 4. Боевой режим | пороги из оптимизации, ¼ Kelly, первые 30 дней × 0,5 | 50+ сделок, Sharpe > 1,0, просадка < 15% |
| 5. Автоисполнение | `IBAdapter`, `FreedomAdapter` (Tradernet), `outside_rth=False` | ордера проходят в paper-аккаунте брокера; стопы не срабатывают вне сессии |

---

## 15. Правила для Claude Code

Вынесены в `CLAUDE.md`. Порядок работ — `TASKS.md`.

---

## 16. Открытые вопросы (закрыть до или во время фазы 0)

- [x] (решено 13.10.2026: Options Starter + Stocks Starter, Benzinga заменён Finnhub и Alpha Vantage — `OPEN_QUESTIONS.md`) Текущий тариф Massive у заказчика: Options Developer ($79, задержка 15 мин, 4 года) или Advanced ($199, реальное время, 5+ лет); нужен ли Benzinga Earnings ($99).
- [x] (решено 14.10.2026: IV в истории Massive нет, только цены сделок; IV и греки пересчитываются по Блэку–Шоулзу) Есть ли в истории Massive значения IV или их нужно пересчитывать из цен опционов.
- [ ] IVolatility Backtest Plus ($149): отложено решением заказчика 14.10.2026 — на старте архив Massive за 2 года; покупка — если по итогам бэктеста T12 событий мало.
- [x] Второй источник даты отчёта — решено 13.10.2026: Alpha Vantage `EARNINGS_CALENDAR` (основной — Finnhub).
- [ ] Polymarket: доступ из юрисдикции заказчика, ликвидность рынков на отчёты, правила расчёта.
- [ ] Брокер: IB или Freedom; поддержка опционов США через API; запрет срабатывания стопов вне основной сессии.
- [ ] Капитал модуля, риск на сделку, лимиты кластера и сезона — значения для `thresholds.yaml`.
- [ ] Список 30–50 компаний и секторов для первого сезона.

---

## 17. Пять улучшений (входят в MVP)

1. **Меньше признаков.** Старт — 6–8 признаков, бюджет активных — 12 (`thresholds.yaml: feature_budget`). Новый признак — только через путь плагина. Команда `learn season` выводит вклад каждого признака (модель с ним и без); признак без улучшения Brier помечается к отключению.
2. **Один экран отбора.** Эндпоинт `GET /api/week` и экран «Неделя»: все события ближайших 5 торговых дней, сортировка по `EV × размер` (не по уверенности). Топ-5 — режим, конструкция, ожидаемая прибыль; остальные — коды пропуска. Тот же список уходит в понедельничный дайджест 08:30 ET. Других рейтингов в системе нет.
3. **Реальные издержки.** Модуль `execution/costs.py`, интерфейс `CostModel` (комиссия за акцию и за опционный контракт, половина спреда на входе и выходе по фактическим котировкам, проскальзывание на открытии). Обязателен в Paper, теневых сделках, бэктесте и в пороге `edge > costs + 0.03`. После реальных сделок — калибровка по исполнениям; расхождение Paper и реальности > 20% → алерт СИСТЕМА.
4. **Порядок включения режимов.** В `registry.yaml` на старте: режим C и стратегии на `move_ratio` (стрэддл, iron condor) — `paper`; режим A — `shadow` до бэктеста; режим B — `shadow` до 30+ наблюдений с Brier лучше базового.
5. **Независимость от брокера.** Вся логика — через `BrokerAdapter`; брокер выбирается в `config` (`broker: manual | ib | freedom`). У каждой реализации своя `CostModel`. Тест: смена брокера не меняет ни одного файла вне `adapters/broker/` и `config/`.

---

## Источники

- Massive — тарифы: https://massive.com/pricing , https://massive.com/pricing?product=options
- Massive — новости: https://massive.com/docs/rest/stocks/news
- Finnhub — API: https://finnhub.io/docs/api , схема https://finnhub.io/static/swagger.json
- Alpha Vantage — API: https://www.alphavantage.co/documentation/
- IVolatility — исторические данные: https://ivolatility.com/historical-options-data
- IVolatility — API и тарифы: https://www.ivolatility.com/data-cloud-api/
- Архитектура системы (документ): Earnings Engine — архитектура системы
