# Фикстуры Alpha Vantage

**Записаны 13.10.2026** публичным демо-ключом из документации (`apikey=demo`, работает только для IBM и рыночного календаря).

| Файл | Запрос | Примечание |
|---|---|---|
| `earnings_ibm.json` | `EARNINGS&symbol=IBM` | урезан: 3 годовых и 8 квартальных строк |
| `earnings_estimates_ibm.json` | `EARNINGS_ESTIMATES&symbol=IBM` | урезан до 8 горизонтов |
| `earnings_calendar.csv` | `EARNINGS_CALENDAR&horizon=3month` | выборка: 12 компаний вселенной + 2 строки с пустым временем |
| `earnings_calendar_information.csv` | `EARNINGS_CALENDAR&symbol=IBM` с демо-ключом | заглушка: заголовок CSV и строка `I,n,f,o,r,m,a` вместо данных |
| `information.json` | `EARNINGS_ESTIMATES&symbol=GS` с демо-ключом | заглушка `{"Information": ...}` при HTTP 200 |
