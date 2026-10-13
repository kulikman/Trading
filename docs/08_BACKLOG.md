# Backlog

## How to Use

Work through tasks **one at a time**. Before starting a task:
1. Read `09_CURRENT_STATUS.md`
2. Read `10_AI_RULES.md` (in `.claude/rules/`)
3. Read `04_ARCHITECTURE.md`
4. Move task status to `In Progress`
5. After completion: update `09_CURRENT_STATUS.md` and mark `Done`

## Statuses
`Todo` · `In Progress` · `Review` · `Testing` · `Done` · `Blocked`

## Priorities
`P0: Critical` · `P1: Important` · `P2: Normal` · `P3: Later`

---

## Template Setup Tasks

---

### SETUP-001: Configure Supabase project

**Priority:** P0 | **Status:** Todo

**Description:** Connect the template to a real Supabase project.

**Steps:**
1. Create project at supabase.com
2. Copy project URL and anon key to `.env.local`
3. Copy service role key to `.env.local`
4. Run `pnpm supabase link --project-ref <id>`
5. Run `pnpm supabase db push` to apply migrations

**Acceptance Criteria:**
- [ ] `pnpm dev` connects to Supabase without errors
- [ ] Auth sign-up creates a row in `profiles`

---

### SETUP-002: Configure Stripe

**Priority:** P0 | **Status:** Todo

**Description:** Connect Stripe for payments.

**Steps:**
1. Create products and prices in Stripe dashboard
2. Set env vars: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
3. Set `STRIPE_PRODUCT_ID_PRO`, `STRIPE_PRICE_ID_PRO` (and team if needed)
4. Add webhook endpoint in Stripe: `https://[domain]/api/webhooks/stripe`
5. Test with Stripe CLI: `stripe listen --forward-to localhost:3000/api/webhooks/stripe`

**Acceptance Criteria:**
- [ ] Checkout flow completes successfully
- [ ] Webhook updates `subscriptions` table

---

### SETUP-003: Configure Resend email

**Priority:** P1 | **Status:** Todo

**Steps:**
1. Add domain in Resend dashboard and verify DNS
2. Set `RESEND_API_KEY` and `RESEND_FROM_EMAIL` in `.env.local`
3. Test welcome email on signup

---

### SETUP-004: Configure PostHog analytics

**Priority:** P2 | **Status:** Todo

**Steps:**
1. Create project at posthog.com
2. Set `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_HOST`

---

## Product Tasks

> Add your product-specific tasks below. Copy the template:

---

### TASK-XXX: [Task name]

**Epic:** [Epic number]
**Priority:** P0/P1/P2/P3 | **Status:** Todo

**Description:**
[What needs to be built and why]

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2

**Technical Notes:**
[Files likely to change, approach, constraints]

**Test Notes:**
[How to verify this works]

---
