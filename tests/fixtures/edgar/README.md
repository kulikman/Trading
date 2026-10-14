# Фикстуры SEC EDGAR

| Файл | Запрос | Происхождение |
|---|---|---|
| `submissions_gs.json` | `GET https://data.sec.gov/submissions/CIK0000886982.json` | **записан** 13.10.2026, урезан: 14 подач 8-K / 10-Q / 10-K и 3 проспекта 424B2 (для проверки фильтра), метаданные |
| `companyfacts_gs.json` | `GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000886982.json` | **записан** 13.10.2026, урезан: 5 показателей, факты с 2024 г. |
| `company_tickers.json` | `GET https://www.sec.gov/files/company_tickers.json` | **записан** 14.10.2026 с `SEC_USER_AGENT`, урезан до GS, JPM, NVDA (в полном файле есть все 50 компаний вселенной) |

Без контакта в User-Agent `www.sec.gov` отвечает 403 (проверено 13.10.2026).

| Файл | Запрос | Примечание |
|---|---|---|
| `submissions_bac.json` | `GET /submissions/CIK0000070858.json` | **записан** 14.10.2026, урезан: 2 подачи из `recent` (11 475 у банка — меньше года) и 2 записи `files` |
| `CIK0000070858-submissions-002.json` | `GET /submissions/CIK0000070858-submissions-002.json` | **записан** 14.10.2026, урезан до 2 подач: 8-K п. 2.02 от 16.07.2025 и 424B2; формат — те же параллельные массивы, что `recent` |
