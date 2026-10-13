---
name: SaaS Template Audit — реализованные улучшения
description: Что было реализовано в рамках аудита Template-Projects
type: project
---

Аудит и реализация улучшений Template-Projects завершены.

**Why:** Шаблон имел ряд критических пробелов для продакшна.
**How to apply:** При работе с шаблоном учитывать что всё перечисленное уже реализовано.

## Реализовано

1. **Upstash Redis rate limiting** — `src/lib/rate-limit.ts` теперь использует Upstash когда есть env vars, fallback на in-memory для dev
2. **Signup flow** — `src/app/(auth)/signup/` с rate limit (3/min), email verification через Supabase, welcome email через Resend
3. **Forgot/reset password** — `/forgot-password` и `/reset-password` с защитой от email enumeration
4. **Auth callback** — `src/app/auth/callback/route.ts` для Supabase email confirmation + OAuth
5. **Stripe** — checkout session API, customer portal API, полный webhook handler (subscription created/updated/deleted), billing settings page
6. **shadcn Form компоненты** — `Input`, `Label`, `Form` с react-hook-form интеграцией
7. **Sentry** — `sentry.client.config.ts`, `sentry.server.config.ts`, `onRequestError` в instrumentation.ts
8. **Audit log** — migration `0003_audit_log.sql`, utility `src/lib/audit.ts`, подключено к login/signup
9. **Playwright E2E** — `playwright.config.ts`, тесты для auth flow и billing

## Новые файлы

- `supabase/migrations/0002_billing.sql` — subscriptions таблица + stripe_customer_id на profiles
- `supabase/migrations/0003_audit_log.sql` — audit_logs таблица
- `src/types/database.ts` — обновлён с типами profiles, subscriptions, audit_logs (+ Relationships)
- `src/lib/stripe.ts` — Stripe client singleton, getOrCreateStripeCustomer
- `src/lib/audit.ts` — writeAuditLog utility
- `src/app/settings/` — Settings + Billing pages
- `tests/e2e/` — Playwright tests

## Добавленные пакеты

- `@upstash/ratelimit`, `@upstash/redis`
- `stripe` (v22, API version "2026-04-22.dahlia")
- `react-hook-form`, `@hookform/resolvers`
- `@sentry/nextjs`
- `@playwright/test`

## Важные детали

- Stripe v22: `current_period_start/end` на `SubscriptionItem`, не на `Subscription`
- `GenericTable` требует `Relationships: []` поле в database.ts
- Typed routes требуют `pnpm build` или `pnpm dev` после добавления новых routes
- `onRequestError` — собственный хук Next.js, не экспорт из Sentry
