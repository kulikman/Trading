# Test Plan

## Test Stack
- **Vitest** — unit + integration tests (colocated: `utils.ts` → `utils.test.ts`)
- **Playwright** — E2E tests for critical user flows
- **Manual QA** — before every production deploy

---

## Critical User Flows to Test

### Flow 1: Authentication

| Step | Action | Expected |
|---|---|---|
| 1 | Open `/login` | Login page renders |
| 2 | Submit valid email/password | Redirect to `/onboarding` (new user) or `/dashboard` |
| 3 | Reload page | Session persists, stays logged in |
| 4 | Visit protected route while logged out | Redirect to `/login` |
| 5 | Click logout | Session cleared, redirect to `/` |
| 6 | Submit wrong password | Error message shown, no crash |

**Status:** ⬜ Not tested / ✅ Passing / ❌ Failing

---

### Flow 2: Onboarding

| Step | Action | Expected |
|---|---|---|
| 1 | New user completes auth | Redirect to `/onboarding` |
| 2 | Complete all steps | `profiles.onboarding_completed = true` |
| 3 | Redirect to dashboard | `/dashboard` loads correctly |
| 4 | Re-visit `/onboarding` | Redirect to `/dashboard` (already completed) |

**Status:** ⬜ Not tested

---

### Flow 3: Stripe Checkout

| Step | Action | Expected |
|---|---|---|
| 1 | Click "Upgrade to Pro" | Stripe Checkout opens |
| 2 | Complete payment with test card `4242...` | `checkout.session.completed` webhook fires |
| 3 | Return to app | `subscriptions` row has `status = active` |
| 4 | Feature gate is lifted | `<PlanGate>` content visible |

**Status:** ⬜ Not tested

---

### Flow 4: Core Feature

| Step | Action | Expected |
|---|---|---|
| 1 | Navigate to feature page | Page loads, empty state shown |
| 2 | Create new item | Item appears in list |
| 3 | Edit item | Changes saved |
| 4 | Delete item | Item removed |
| 5 | Log in as different user | Cannot see first user's items |

**Status:** ⬜ Not tested

---

## Unit Tests (Vitest)

### Already Written (template)
- [x] `src/lib/utils.test.ts` — `cn()` utility
- [x] `src/lib/constants.test.ts` — Route segments have labels

### To Write for Your Features
- [ ] `src/lib/plan-limits.test.ts` — Plan limits per product ID
- [ ] `src/lib/validations.test.ts` — Zod schemas for your domain
- [ ] `src/features/[feature]/lib/*.test.ts` — Business logic

---

## Backend Tests

- [ ] Server Actions return correct data for valid input
- [ ] Server Actions throw for invalid input (Zod validation)
- [ ] Server Actions throw for unauthenticated requests
- [ ] Stripe webhook handler verifies signature
- [ ] Stripe webhook handler rejects invalid events
- [ ] API key verification rejects unknown keys
- [ ] Cron endpoint rejects missing CRON_SECRET

---

## Security Tests

- [ ] Unauthenticated user cannot access `/dashboard/*`
- [ ] User A cannot read/write User B's data (test RLS)
- [ ] Admin routes return 403 for regular users
- [ ] Webhook endpoint returns 400 for invalid signature
- [ ] API endpoints reject missing/invalid API keys
- [ ] No secrets visible in client bundle (`pnpm build` output)

---

## Pre-deploy Checklist

Before every production deploy:

- [ ] `pnpm tsc --noEmit` — no TypeScript errors
- [ ] `pnpm lint` — no ESLint errors
- [ ] `pnpm test` — all tests passing
- [ ] `pnpm build` — build succeeds, check bundle output for size regressions
- [ ] Manual smoke test of auth flow
- [ ] Manual smoke test of core feature
- [ ] Environment variables verified in Vercel dashboard
- [ ] Database migrations applied (`pnpm supabase db push`)
- [ ] No `console.log` in source code
- [ ] No hardcoded secrets
