# Integration Map

> How external services connect. Reference before touching auth, billing, or storage.

---

## Supabase

| Layer | How we use it | Key files |
|---|---|---|
| Auth | Email/password + OAuth. Session refreshed on every request via `proxy.ts`. | `src/lib/supabase/`, `src/proxy.ts` |
| Database | PostgreSQL with RLS. All tables have RLS enabled. `service_role` key server-only. | `supabase/migrations/` |
| Storage | File uploads. Buckets TBD per feature. | `src/features/*/api/actions.ts` |
| Realtime | Push changes to client (notifications bell, live lists). | `src/features/notifications/` |

**Client types:**
- `createBrowserClient()` — client components, browser only
- `createServerClient()` — server components, server actions, route handlers
- `createAdminClient()` — server only, bypasses RLS, use sparingly

---

## Stripe

| Flow | Route / file |
|---|---|
| Checkout | `src/app/api/stripe/checkout/route.ts` |
| Customer portal | `src/app/api/stripe/portal/route.ts` |
| Webhooks | `src/app/api/webhooks/stripe/route.ts` |
| Billing settings | `src/app/settings/billing/` |

Stripe customer ID stored in `profiles.stripe_customer_id`.
Subscription state in `public.subscriptions` table — written by webhook handler only.

**Test mode:** Use Stripe CLI `stripe listen --forward-to localhost:3000/api/webhooks/stripe`.

---

## Resend (email)

| Trigger | Template location |
|---|---|
| Welcome | `src/lib/email/templates.ts` |
| Password reset | Handled by Supabase Auth (built-in) |
| Subscription events | `src/lib/email/templates.ts` |

Key: `RESEND_API_KEY`. From address: `RESEND_FROM_EMAIL` (must be verified domain).

---

## PostHog (analytics)

Initialised in `src/components/analytics/posthog-provider.tsx`.
- Client-side: `usePostHog()` hook → `ph.capture("event_name", props)`
- Server-side: `trackServerEvent()` from `src/lib/analytics.ts`
- Key: `NEXT_PUBLIC_POSTHOG_KEY`

Identify users after login:
```ts
const ph = usePostHog()
ph.identify(user.id, { email: user.email, plan: limits.name })
```
Reset on sign-out:
```ts
ph.reset()
```

---

## Sentry (error tracking)

Configured in `sentry.client.config.ts` and `sentry.server.config.ts`.
Auto-captures unhandled errors. Use `Sentry.captureException(err)` for manual captures.
Key: `NEXT_PUBLIC_SENTRY_DSN`.

---

## Upstash Redis (rate limiting)

Used by `src/lib/rate-limit.ts` as the backing store for `@upstash/ratelimit`.
Falls back to in-memory limiter when `UPSTASH_REDIS_REST_URL` is unset (safe for dev).

---

## Vercel

- Analytics: `@vercel/analytics` — enabled via `NEXT_PUBLIC_FF_ANALYTICS` flag
- Speed Insights: `@vercel/speed-insights` — same flag
- Cron jobs: add to `vercel.json` `crons` array; route handlers verify `CRON_SECRET`
- Env vars: use `vercel env pull .env.local` to sync production vars to local dev
