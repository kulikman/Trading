# Rule: Security

> Читается агентами security и reviewer перед любым аудитом или review.

## Supabase RLS

- RLS включён на **каждой** таблице. Политики пишутся в той же миграции, что создаёт таблицу.
- `service_role` ключ — только на сервере. Никогда не импортируй `@/lib/supabase/admin.ts` из файла с `"use client"`.
- На сервере используй `supabase.auth.getUser()` (не `getSession()`) — он ревалидирует против Supabase Auth.
- Для чувствительной логики (webhooks, 3rd-party API с секретами) → Edge Functions.
- Любое изменение таблиц без RLS в той же поставке должно считаться blocker.

## Environment Variables

- Все env vars проходят через Zod-схему в `src/lib/env.ts`.
- Добавляя новый env var — обнови `.env.example`, `src/lib/env.ts` и CI workflow.
- Никогда не коммить `.env.local` или `.env` с реальными значениями.
- Никогда не выдумывай env vars, ключи интеграций или секреты, которых нет в коде и документации.

## Auth

- Проверяй auth на каждом protected route, Server Action и Route Handler через `supabase.auth.getUser()`.
- Никогда не логируй чувствительные данные (пароли, токены, PII).

## API

- Санитизируй все user inputs через Zod на API boundary.
- Валидируй и на клиенте (UX) и на сервере (безопасность).
- CORS headers не ставить `*` на чувствительных routes.

## Security Headers

- CSP и security headers настроены в `src/proxy.ts` — не перекрывай их.
- Keep `next` на patched версии (16.2.4+) из-за CVE-2025-66478.

## Protected Files

Не изменяй без явной причины и понимания эффекта:

- `supabase/migrations/**`
- `src/lib/supabase/admin.ts`
- `src/proxy.ts`
- `src/types/database.ts`
- `src/app/api/webhooks/stripe/**`
- `src/app/auth/callback/**`

## Watch List

- `"use client"` компоненты импортирующие `lib/supabase/admin.ts` → НИКОГДА
- API routes без `supabase.auth.getUser()` → ВСЕГДА добавлять
- Raw `process.env` без `env.ts` → использовать `getServerEnv()` / `getClientEnv()`
- Новые таблицы без RLS → заблокировать до написания политик
