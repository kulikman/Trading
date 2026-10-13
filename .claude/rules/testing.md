# Rule: Testing

> Читается агентами tester и coder при написании тестов.

## Стек

- **Vitest** — unit и integration тесты
- **Playwright** — E2E когда нужно (auth flows, критичные user journeys)
- **ai-evals** — тесты качества AI-агентов и бизнес-логики (в `tests/ai-evals/`)

## Правила

- Тест-файлы коллоцируются с исходником: `utils.ts` → `utils.test.ts`
- Каждая новая utility function получает тест
- Тесты пиши для: utility functions, API routes, сложной бизнес-логики, Zod schemas
- Минимум 1 happy path + 1 edge case + 1 error case на каждую функцию

## Структура теста

```ts
import { describe, it, expect } from "vitest"

describe("functionName()", () => {
  it("does the thing correctly", () => {
    expect(fn(input)).toBe(expected)
  })

  it("handles edge case X", () => {
    expect(fn(edgeInput)).toEqual(edgeExpected)
  })

  it("throws when invalid input", () => {
    expect(() => fn(badInput)).toThrow("Expected error message")
  })
})
```

## AI Evals (`tests/ai-evals/`)

Тесты не кода, а логики агентов и промптов:

- Агент reviewer всегда находит отсутствующий RLS
- Агент architect предлагает правильную схему для multi-tenant
- Агент security не пропускает захардкоженные секреты
- Критичные бизнес-сценарии: расчёт инвойса, обработка платежа, auth flow

## CI

- `pnpm test` запускается в CI до build
- Build не запускается если тесты не прошли
- Production dependency audit is a blocking CI gate: `pnpm audit:prod`
- Local verification must include every blocking CI gate, not only unit tests
  and type checks.
- After pushing, watch GitHub Actions until required checks are successful.
- Coverage не обязателен, но важна полнота покрытия критичных путей
