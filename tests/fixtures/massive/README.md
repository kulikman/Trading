# Фикстуры Massive

**Это не записанные ответы живого API.** Ключа Massive пока нет (`OPEN_QUESTIONS.md`), поэтому файлы собраны
по схеме ответов и примерам из документации massive.com/docs (13.10.2026). Числа условные.

| Файл | Эндпоинт |
|---|---|
| `aggs_gs_page1.json`, `aggs_gs_page2.json` | `GET /v2/aggs/ticker/{ticker}/range/...` (вторая страница — по `next_url`) |
| `last_nbbo_gs.json` | `GET /v2/last/nbbo/{ticker}` |
| `snapshot_gs.json` | `GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}` |
| `options_contracts_gs.json` | `GET /v3/reference/options/contracts` |
| `option_chain_gs.json` | `GET /v3/snapshot/options/{underlyingAsset}` |

Цепочка GS: цена 897.00, экспирации 16.10.2026 и 23.10.2026, страйки 890 / 900 / 910.
ATM-страйк 900: колл 20.00 + пут 23.00 = стрэддл 43.00, implied move = 43 / 897 ≈ 4,79%.

После получения ключа: записать реальные ответы теми же именами и прогнать контрактные тесты.
