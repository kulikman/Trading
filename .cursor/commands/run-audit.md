---
description: Run audit — полный аудит Template-Projects, при необходимости обновляет rules.json
---

Выполни полный аудит репозитория **Template-Projects** строго по инструкции в `audit/AUDIT_PROMPT.md`.

1. Прочитай `audit/rules.json` и `CLAUDE.md`.
2. Проверь дерево `src/` (в т.ч. `src/app/`, `src/lib/`, `src/components/`) и конфиги на соответствие каждому правилу; сформируй отчёт с таблицей статусов.
3. Допиши запись в `audit/audit-history.json` в массив `entries`.
4. Если обнаружены конфликты между правилами — задокументируй разрешение в `audit/conflicts.log`.
5. Если уместно расширить базу — предложи новые правила; по явному согласию пользователя обнови `audit/rules.json` (валидный JSON, уникальные id, обнови `meta`).

После изменений в коде запусти `pnpm lint` и `pnpm tsc --noEmit`.
