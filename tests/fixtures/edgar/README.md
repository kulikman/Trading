# Фикстуры SEC EDGAR

| Файл | Запрос | Происхождение |
|---|---|---|
| `submissions_gs.json` | `GET https://data.sec.gov/submissions/CIK0000886982.json` | **записан** 13.10.2026, урезан: 14 подач 8-K / 10-Q / 10-K и 3 проспекта 424B2 (для проверки фильтра), метаданные |
| `companyfacts_gs.json` | `GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000886982.json` | **записан** 13.10.2026, урезан: 5 показателей, факты с 2024 г. |
| `company_tickers.json` | `GET https://www.sec.gov/files/company_tickers.json` | **записан** 14.10.2026 с `SEC_USER_AGENT`, урезан до GS, JPM, NVDA (в полном файле есть все 50 компаний вселенной) |

Без контакта в User-Agent `www.sec.gov` отвечает 403 (проверено 13.10.2026).
