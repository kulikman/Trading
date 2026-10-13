# Command: /project:review

Запускает полный code review текущей или указанной области кода.

## Использование

```
/project:review                    # review текущего открытого файла
/project:review src/features/auth/ # review папки
/project:review security           # security-focused review
```

## Что делает

1. Читает `.claude/agents/reviewer.md`
2. Применяет чеклист из rules/code-style.md + rules/security.md
3. Выдаёт структурированный отчёт: blockers / warnings / ✅ OK

## Output

```
## Code Review: [scope]

### ❌ Блокирует merge
### ⚠️ Предупреждения  
### ✅ Хорошо
### 📝 Итог
```
