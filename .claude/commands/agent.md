# Command: /project:agent

Запускает конкретного El Aurion агента с задачей.

## Использование

```
/project:agent [имя агента] "[задача]"

/project:agent orchestrator "добавь модуль инвойсов с CRUD и RLS"
/project:agent coder "реализуй фильтрацию по дате в таблице транзакций"
/project:agent reviewer "проверь src/features/invoices/"
/project:agent architect "спроектируй схему для multi-tenant billing"
/project:agent tester "напиши тесты для src/lib/calculations.ts"
/project:agent security "аудит API routes в src/app/api/"
```

## Агенты

| Имя | Когда использовать |
|-----|-------------------|
| `orchestrator` | Сложная задача с несколькими шагами |
| `coder` | Написать или изменить код |
| `reviewer` | Проверить код перед merge |
| `architect` | Спроектировать схему, API, структуру |
| `tester` | Написать тесты |
| `security` | Аудит безопасности |

## Процесс

1. Агент читает свой файл из `.claude/agents/[name].md`
2. Читает нужные rules из `.claude/rules/`
3. Выполняет задачу согласно своей роли
4. Обновляет `.claude/memory/` если нужно
