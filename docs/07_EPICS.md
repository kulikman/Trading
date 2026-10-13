# Epics

## Statuses
`Not Started` · `In Progress` · `Blocked` · `Review` · `Done`

---

## Epic 1: Project Setup ✅ (template scaffolded)

**Goal:** Working development environment, CI/CD, deployment.

**Included in this template:**
- [x] Next.js 16 + TypeScript + Tailwind v4
- [x] Supabase integration (client, server, admin, proxy)
- [x] Environment variable validation (Zod)
- [x] ESLint + Prettier + commitlint
- [x] Vitest unit tests
- [x] semantic-release + CHANGELOG
- [x] Vercel deployment config
- [x] knip dead-code detection

---

## Epic 2: Authentication ✅ (template scaffolded)

**Goal:** Users can sign up, log in, reset password, manage session.

**Included in this template:**
- [x] Email/password auth via Supabase
- [ ] OAuth provider buttons/actions (callback route is ready for future OAuth flows)
- [x] Password reset email flow via Supabase Auth
- [x] Auth callback with onboarding redirect
- [x] Session refresh in `proxy.ts`
- [x] Protected routes via `proxy.ts` matcher
- [x] Profile creation trigger on signup

---

## Epic 3: Onboarding ✅ (template scaffolded)

**Goal:** New users are guided to their first value moment.

**Included:**
- [x] Multi-step onboarding wizard (`/onboarding`)
- [x] Steps defined in `src/features/onboarding/lib/steps.ts`
- [x] `profiles.onboarding_completed` flag
- [x] Auth callback redirects new users to onboarding

**To customize:**
- [ ] Update steps in `src/features/onboarding/lib/steps.ts`
- [ ] Add product-specific onboarding questions

---

## Epic 4: Core Product Feature

**Goal:** [What the main feature does]

**Status:** Not Started

### Tasks
- [ ] Define data model → add to `docs/05_DATABASE_SCHEMA.md`
- [ ] Write migration
- [ ] Create Server Actions
- [ ] Create Server Components (list + detail pages)
- [ ] Create client forms
- [ ] Add to nav in `src/config/site.ts`
- [ ] Add route to `src/lib/constants.ts`
- [ ] Add breadcrumb label to `src/components/layout/breadcrumbs.tsx`
- [ ] Write unit tests
- [ ] Wire up PostHog events

### Acceptance Criteria
- [ ] User can create [entity]
- [ ] User can view [entity]
- [ ] User can update [entity]
- [ ] User cannot access another user's [entity]
- [ ] Free tier limit enforced via `<PlanGate>`

---

## Epic 5: Payments & Subscriptions ✅ (template scaffolded)

**Goal:** Users can upgrade to paid plans; revenue flows in.

**Included:**
- [x] Stripe Checkout integration
- [x] Webhook handler (`checkout.completed`, `subscription.updated`, `invoice.payment_failed`)
- [x] `upsertSubscription()` keeps DB in sync
- [x] `getPlanLimits()` driven by env var product IDs
- [x] `<PlanGate>` component for feature gating
- [x] Billing settings page (`/settings/billing`)
- [x] Usage page (`/settings/usage`)

**To configure:**
- [ ] Set `STRIPE_PRODUCT_ID_PRO`, `STRIPE_PRODUCT_ID_TEAM`, `STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_TEAM` in Vercel env
- [ ] Update limits in `src/lib/plan-limits.ts`

---

## Epic 6: Notifications ✅ (template scaffolded, feature-flagged)

**Goal:** Users see real-time in-app notifications.

**Enable:** Set `NEXT_PUBLIC_FF_NOTIFICATIONS=true`

**Included:**
- [x] `<NotificationsBell>` with Supabase Realtime badge
- [x] `sendNotification(userId, { title, body, kind, href })` server helper
- [x] Auto-cleanup of old notifications (cron job)

---

## Epic 7: Organizations / Teams ✅ (template scaffolded)

**Goal:** Multiple users can collaborate within a workspace.

**Included:**
- [x] `orgs` + `org_members` tables with RLS
- [x] Create org form (`/settings/organization`; legacy `/settings/org` redirects)
- [x] Org list with member counts

**To implement:**
- [ ] Invite flow (email invite → accept link)
- [ ] Org-scoped data (add `org_id` FK to core tables)
- [ ] Role management within org

---

## Epic 8: Admin Panel

**Goal:** Internal team can manage users and platform data.

**Status:** Not Started

### Tasks
- [ ] Create `/admin` route group with role guard
- [ ] Users list with search and role filter
- [ ] Subscription overview
- [ ] Audit log viewer
- [ ] Impersonate user (super_admin only)

---

## Epic 9: Testing & QA

**Goal:** Critical flows are tested; CI enforces quality gates.

**Included:**
- [x] Vitest unit tests for utilities and Zod schemas
- [x] CI pipeline (pnpm tsc + lint + test)

**To add:**
- [ ] Playwright E2E for auth flow
- [ ] Playwright E2E for checkout flow
- [ ] Playwright E2E for core feature flow
