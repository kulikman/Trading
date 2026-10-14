# Фикстуры Massive

| Файл | Эндпоинт | Происхождение |
|---|---|---|
| `aggs_gs_recorded.json` | `GET /v2/aggs/ticker/GS/range/1/day/2026-10-01/2026-10-12` | **записан** 13.10.2026 |
| `options_contracts_gs.json` | `GET /v3/reference/options/contracts` | **записан** 13.10.2026 (первая страница, с `next_url`) |
| `snapshot_gs.json` | `GET /v2/snapshot/locale/us/markets/stocks/tickers/GS` | **записан** 13.10.2026 — тариф без котировок и сделок: `lastQuote` / `lastTrade` нет; `day.dv`, `min.dv` — строки |
| `news_gs.json` | `GET /v2/reference/news?ticker=GS&limit=3` | **записан** 13.10.2026 (с `next_url`) |
| `not_entitled.json` | `GET /v3/snapshot/options/GS` | **записан** 13.10.2026 — ответ 403 `NOT_AUTHORIZED` на текущем тарифе |
| `history_contracts_nflx.json` | `GET /v3/reference/options/contracts?underlying_ticker=NFLX&as_of=2024-10-17&expiration_date.gte=2024-10-18&expiration_date.lte=2024-11-01&strike_price.gte=680&strike_price.lte=695` | **записан** 14.10.2026, выборка 24 контракта (экспирации 18.10 и 25.10) |
| `history_aggs_nflx241018c00687500.json`, `history_aggs_nflx241018p00687500.json` | `GET /v2/aggs/ticker/O:NFLX241018{C,P}00687500/range/1/day/2024-10-10/2024-10-19` | **записаны** 14.10.2026 — 5 свечей: доступ начинается 14.10.2024 (2 года назад) |
| `aggs_gs_page1.json`, `aggs_gs_page2.json` | свечи, пагинация по `next_url` | собран по документации |
| `last_nbbo_gs.json` | `GET /v2/last/nbbo/{ticker}` | собран по документации (на текущем тарифе — 403) |
| `option_chain_gs.json` | `GET /v3/snapshot/options/{underlyingAsset}` | собран по документации (на текущем тарифе — 403) |

Записанные ответы — с ключа Massive из Elaurion-Options; ключ в файлы не попадает (проверено).
Собранные по документации — по схеме и примерам massive.com/docs (13.10.2026), числа условные.

Цепочка GS (собранная): цена 897.00, экспирации 16.10.2026 и 23.10.2026, страйки 890 / 900 / 910.
ATM-страйк 900: колл 20.00 + пут 23.00 = стрэддл 43.00, implied move = 43 / 897 ≈ 4,79%.

После подключения тарифа с цепочкой опционов — записать `option_chain_gs.json` вживую и прогнать тесты.

Исторический отчёт NFLX 17.10.2024 (AMC, записанный): акция 687.65, страйк 687.5, экспирация 18.10.2024.
Колл 25.57 + пут 25.27 = 50.84, implied move = 50.84 / 687.65 ≈ 7,39% — сверено вручную.
