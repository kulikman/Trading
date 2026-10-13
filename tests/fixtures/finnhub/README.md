# Фикстуры Finnhub

**Не записанные ответы.** Ключа Finnhub пока нет (заказчик заведёт позже). Файлы собраны по схеме API
https://finnhub.io/static/swagger.json (13.10.2026): `EarningsCalendar` / `EarningRelease` и массив `EarningResult`. Числа условные.

| Файл | Эндпоинт |
|---|---|
| `earnings_calendar.json` | `GET /calendar/earnings` — `hour` = bmo / amc / dmh / пусто; ZZZZ — тикер не из вселенной; TSLA — без оценок |
| `stock_earnings_gs.json` | `GET /stock/earnings` — массив на верхнем уровне |

После получения `FINNHUB_API_KEY` — записать реальные ответы теми же именами и прогнать тесты.
