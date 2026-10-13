# Система аудита — Template-Projects

Пять файлов и как их использовать в этом шаблоне.

| Файл | Назначение |
|------|------------|
| `.cursorrules` | Cursor подхватывает автоматически — поведение агента и сценарии аудита. |
| `audit/rules.json` | База правил. Агент может дополнять по итогам аудита. |
| `audit/AUDIT_PROMPT.md` | Промпт полного прогона: Composer или команда **Run audit**. |
| `audit/audit-history.json` | История запусков — агент дописывает записи в `entries`. |
| `audit/conflicts.log` | Разрешения, когда два правила противоречат друг другу. |

Структура кода в правилах и промпте ориентирована на этот репозиторий: **`src/app/`**, **`src/components/`**, **`src/lib/`**, корневые конфиги, **`.github/workflows/`**.

## Форк шаблона

После `git clone` / переименования пакета пути `audit/*` и `.cursorrules` остаются валидными. Если переносишь папку аудита в другой проект вручную:

```bash
# Из клона Template-Projects в новый репозиторий
cp .cursorrules /path/to/your-app/
cp -r audit /path/to/your-app/
```

Если в источнике каталог назывался `.audit`, переименуй в `audit/` или обнови ссылки в `.cursorrules` и `.cursor/commands/*.md`.

## Команды Cursor

Файлы в `.cursor/commands/`:

| Команда | Эффект |
|---------|--------|
| **Run audit** | Полный аудит по `AUDIT_PROMPT.md` + `rules.json`; при необходимости обновляет `rules.json` и пишет в `audit-history.json`. |
| **Fix all critical** | Исправляет нарушения уровня **CRITICAL** из `rules.json`. |
| **Show rules** | Сводка текущей базы из `audit/rules.json`. |
