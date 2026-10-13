# AI Evals

Тесты качества El Aurion агентов и критичной бизнес-логики.

## Что тестируем

- Агент `reviewer` находит типичные проблемы (missing RLS, secrets, any)
- Агент `security` не пропускает уязвимости
- Критичные бизнес-сценарии которые нельзя сломать

## Запуск

```bash
pnpm test tests/ai-evals/
```

## Структура

```
tests/ai-evals/
├── README.md
├── agents/
│   ├── reviewer.eval.ts     # тесты агента reviewer
│   └── security.eval.ts     # тесты агента security
└── business/
    └── [domain].eval.ts     # критичные бизнес-сценарии
```

## Пример eval

```ts
// tests/ai-evals/agents/reviewer.eval.ts
import { describe, it, expect } from "vitest"

describe("Reviewer Agent Evals", () => {
  it("flags missing RLS", () => {
    const codeWithoutRLS = `
      CREATE TABLE invoices (id uuid PRIMARY KEY);
      -- No RLS policy
    `
    // Здесь логика запуска агента и проверки результата
    // Будет реализовано при добавлении AI eval runner
  })
})
```
