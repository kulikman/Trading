---
description: Show rules — показать текущую базу правил из audit/rules.json
---

Прочитай `audit/rules.json` и выведи для пользователя:

1. Версию из `meta` и `ruleCount`.
2. Компактную таблицу: **id** | **severity** | **category** | **title** (все правила из массива `rules`).
3. Одно предложение: сколько правил с severity CRITICAL / HIGH / MEDIUM / LOW.

Не изменяй файлы; только показать сводку.
