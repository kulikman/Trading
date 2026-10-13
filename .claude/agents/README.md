# El Aurion Agents

Система специализированных агентов для разработки и контроля качества.

## Как запускать

В Claude Code используй команду `/project:agent`:

```
/project:agent orchestrator "добавь модуль инвойсов с CRUD и RLS"
/project:agent coder "реализуй фильтрацию по дате в таблице транзакций"
/project:agent reviewer "проверь src/features/invoices/"
/project:agent architect "спроектируй схему для multi-tenant billing"
/project:agent tester "напиши тесты для src/lib/calculations.ts"
/project:agent security "аудит безопасности API routes"
```

## Агенты

| Агент | Роль | Читает rules/ |
|-------|------|---------------|
| `orchestrator` | Декомпозирует задачу, делегирует агентам | все |
| `coder` | Пишет feature код | code-style, architecture, business-context |
| `reviewer` | Code review | code-style, security, architecture |
| `architect` | Проектирует схемы и API | architecture, business-context |
| `tester` | Пишет тесты и ai-evals | testing, business-context |
| `security` | Аудит безопасности | security |

## Принципы

1. **Один агент — одна ответственность.** Coder не делает review, reviewer не пишет код.
2. **Оркестратор — точка входа** для сложных задач. Для простых — вызывай агента напрямую.
3. **Агенты читают rules/** перед работой — не повторяй правила в задаче.
4. **Фиксируй ошибки** в `.claude/memory/mistakes.md` после каждой сессии.
