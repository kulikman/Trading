# Command: /project:test

Пишет или запускает тесты для указанной области.

## Использование

```
/project:test src/lib/calculations.ts   # написать тесты для файла
/project:test invoices                  # тесты для feature
/project:test ai-evals                  # запустить ai evaluations
```

## Процесс

1. Читает `.claude/agents/tester.md`
2. Анализирует код и определяет критичные пути
3. Пишет тесты: happy path + edge cases + error cases
4. Для ai-evals — проверяет что агенты корректно работают

## Output

```
## Tests: [scope]

**Написано тестов:** X
**Покрытые сценарии:**
- [сценарий 1]
- [сценарий 2]

**Не покрыто (и почему):**
- [сценарий] — [причина]
```
