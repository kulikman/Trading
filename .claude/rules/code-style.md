# Rule: Code Style

> Читается каждым агентом перед написанием кода.

## TypeScript

- Strict mode. Никаких `any`. Никаких `@ts-ignore`. Используй `unknown` + narrowing.
- `interface` для форм объектов, `type` для unions/intersections.
- Каждая экспортируемая функция — явный return type.
- Zod на всех границах: API bodies, form inputs, env vars, 3rd-party responses.

## React Components

- Только функциональные компоненты.
- Named exports: `export function ComponentName()`.
- Props interface выше компонента.
- Компоненты не длиннее 150 строк — извлекай логику в хуки или утилиты.
- `"use client"` только для браузерных API, интерактивности или client-only библиотек.
- Server Components получают данные напрямую через `async/await` — никакого `useEffect` для фетчинга.

## Naming

- Файлы: `kebab-case.ts`, `kebab-case.tsx`
- Компоненты: `PascalCase`
- Функции/переменные: `camelCase`
- Константы: `UPPER_SNAKE_CASE`
- Types/Interfaces: `PascalCase`
- Таблицы БД: `snake_case`
- API routes: `kebab-case`
- Булевы: prefix `is`, `has`, `should`, `can`

## Imports

Абсолютные через `@/`. Порядок групп:
1. React / Next.js
2. Внешние библиотеки
3. Внутренние модули (`@/lib`, `@/hooks`, `@/types`)
4. Компоненты (`@/components`)
5. Относительные (только внутри той же feature-папки)

## Error Handling

Никогда не глотай ошибки молча. Всегда логируй или перебрасывай с контекстом:

```ts
try {
  const { data, error } = await supabase.from("users").select("id, email")
  if (error) throw error
  return data
} catch (error) {
  console.error("Failed to fetch users:", error)
  throw new Error("Unable to load users. Please try again.")
}
```

## Verification Discipline

- Не утверждай, что изменение работает, если не запускал подходящие проверки.
- Перед commit сначала исправляй failing checks, потом stage/commit.
- Не делай "быстрый unsafe fix", который обходит правила, типы или проверки ради скорости.

## Запреты

1. Никаких `any` — используй `unknown` и сужай тип.
2. Никаких `console.log` в production путях.
3. Никаких захардкоженных секретов — только через `getServerEnv()` / `getClientEnv()`.
4. Никаких barrel files (`index.ts` re-exports) — ломают tree-shaking.
5. Никаких default exports (кроме Next.js pages/layouts/error boundaries и `proxy.ts`).
6. Никаких данных в `useEffect` — используй Server Components или SWR/React Query.
7. Никаких `middleware.ts` — используй `src/proxy.ts` (Next 16).
