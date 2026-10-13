# Architecture

## System Overview

```text
Browser / Client
  ↓ HTTPS
Vercel Edge (proxy.ts — session refresh + security headers)
  ↓
Next.js App Router (Server Components, Server Actions, Route Handlers)
  ↓                           ↓
Supabase (Postgres + Auth)   External Services
  - RLS on every table         - Stripe (payments + webhooks)
  - Realtime subscriptions     - Resend (transactional email)
  - Storage (file uploads)     - PostHog (analytics)
```

---

## Folder Structure

```
src/
├── app/                        # Next.js App Router
│   ├── (auth)/                 # Auth routes: /login, /signup, /reset-password
│   │   └── auth/callback/      # Email confirmation, password reset, future OAuth callback
│   ├── (dashboard)/            # Protected routes (require auth)
│   │   ├── dashboard/          # Main dashboard
│   │   ├── settings/           # Profile, billing, usage, API keys, org
│   │   └── [your-feature]/     # Core product routes
│   ├── (marketing)/            # Public pages: landing, pricing, docs
│   ├── admin/                  # Admin panel (role: admin/super_admin only)
│   ├── api/
│   │   ├── webhooks/stripe/    # Stripe webhook handler
│   │   └── cron/cleanup/       # Scheduled cleanup job
│   ├── onboarding/             # Onboarding wizard (new users)
│   ├── layout.tsx              # Root layout (metadata, providers)
│   ├── globals.css             # Tailwind v4 theme tokens
│   ├── error.tsx               # Global error boundary
│   ├── not-found.tsx           # 404 page
│   └── loading.tsx             # Global loading skeleton
│
├── components/
│   ├── ui/                     # shadcn/ui primitives (button, input, card…)
│   ├── forms/                  # Reusable form components
│   ├── layout/                 # Header, Footer, Sidebar, Breadcrumbs
│   └── [feature]/              # Feature-specific components
│
├── features/                   # Bounded feature modules (import only via @/features/<name>)
│   ├── orgs/                   # Multi-tenant organizations
│   │   ├── api/                #   actions.ts (Server Actions), create-org.ts (use case + DI)
│   │   ├── lib/                #   org.ts (Supabase queries, repository)
│   │   ├── components/         #   org-create-form.tsx, org-switcher.tsx
│   │   └── index.ts            #   public API re-export
│   ├── onboarding/             # Onboarding wizard feature
│   ├── notifications/          # In-app notifications + bell
│   └── api-keys/               # API key management
│
├── domain/                     # Pure TypeScript domain interfaces (zero external deps)
│   ├── org.ts                  #   OrgRole, OrgMembership, OrgRepository interface
│   └── index.ts                #   re-exports
│
├── lib/
│   ├── supabase/               # client.ts, server.ts, admin.ts, middleware.ts
│   ├── stripe/                 # Stripe client + upsertSubscription
│   ├── email/                  # send.ts + templates/
│   ├── analytics.ts            # PostHog server events
│   ├── plan-limits.ts          # Plan → feature limits map
│   ├── env.ts                  # Zod-validated env vars
│   ├── utils.ts                # cn() + shared utilities
│   ├── constants.ts            # ROUTES map + app-wide constants
│   ├── audit.ts                # AuditAction union + writeAuditLog()
│   ├── auth.ts                 # requireUser() helper
│   ├── rate-limit.ts           # Upstash sliding-window rate limiter
│   └── validations.ts          # Shared Zod schemas (createOrgSchema, loginSchema…)
│
├── hooks/                      # Custom React hooks
├── types/
│   ├── database.ts             # Supabase generated types (auto-generated)
│   └── index.ts                # Shared app types
├── config/site.ts              # Site metadata + nav config
└── proxy.ts                    # Session refresh + security headers (Next 16)
```

---

## Clean Architecture Layers

Dependency direction: **app → features → lib → domain** (never the reverse).

```
src/app/           [Frameworks & Drivers]
  Server Actions, Route Handlers, React Components
  → thin: validate input, compose deps, call use case, revalidate

src/features/[name]/api/  [Use Cases / Application Layer]
  Pure business logic orchestration
  → accepts dependencies as function parameters (DI)
  → testable without vi.mock() — pass stubs directly

src/features/[name]/lib/  [Infrastructure / Interface Adapters]
  Supabase queries, external API calls
  → implements domain interfaces

src/domain/        [Domain / Entities]
  Pure TypeScript interfaces, entity types
  → ZERO external dependencies
```

### Canonical pattern: Use Case with Dependency Injection

```ts
// src/features/orgs/api/create-org.ts
export interface CreateOrgDeps {
  createOrg: (params) => Promise<{ id: string; slug: string }>;
  writeAuditLog: (entry) => Promise<void>;
}

export async function createOrgForUser(params, deps: CreateOrgDeps = defaultDeps) {
  const org = await deps.createOrg(params);
  await deps.writeAuditLog({ action: "org.created", ... });
  return org;
}
```

```ts
// src/features/orgs/api/actions.ts  — thin Server Action
export async function createOrgAction(input: unknown) {
  const user = await requireUser();
  const data = createOrgSchema.parse(input);
  return createOrgForUser({ ...data, userId: user.id }); // deps injected by default
}
```

---

## Key Architecture Rules

1. **Business logic lives in `features/[name]/api/` use cases, not in Server Actions or UI components.**
2. **Server Actions and Route Handlers are thin** — auth check → Zod parse → call use case → revalidate.
3. **Use cases accept deps as parameters** — enables testing without vi.mock(); production deps are defaults.
4. **Domain layer is pure** — `src/domain/` has zero external imports; only TypeScript built-ins.
5. **Supabase access is isolated** — `lib/supabase/server.ts` for server, `lib/supabase/client.ts` for browser, `lib/supabase/admin.ts` for service-role (never import from `"use client"`).
6. **All mutations go through Server Actions** (`"use server"`) — never raw `fetch` to your own API from client.
7. **Caching is opt-in** — use `"use cache"` directive. No implicit memoization (Next 16 behavior).
8. **Auth is checked at every protected route** via `proxy.ts` + `supabase.auth.getUser()`.
9. **External integrations are wrapped** — Stripe in `lib/stripe/`, email in `lib/email/`, etc.
10. **Admin actions are logged** — write to `audit_logs` via `lib/audit.ts` for all destructive operations.
11. **Rate limiting** — `lib/rate-limit.ts` (Upstash sliding window) on all user-facing mutations.

---

## Critical Flows

### Auth Flow

```text
User visits protected route
  ↓
proxy.ts checks session cookie
  ↓ (no session)
Redirect to /login
  ↓
User authenticates (email/OAuth)
  ↓
Supabase sets session cookie
  ↓
auth/callback/route.ts runs:
  - Check profiles.onboarding_completed
  - If false → redirect /onboarding
  - If true  → redirect /dashboard
```

### Stripe Subscription Flow

```text
User clicks "Upgrade"
  ↓
Server Action creates Stripe Checkout Session
  ↓
User completes payment on Stripe hosted page
  ↓
Stripe sends checkout.session.completed webhook
  ↓
api/webhooks/stripe/route.ts:
  - Verifies webhook signature
  - Calls upsertSubscription()
  - Updates profiles.stripe_customer_id
  - Sends subscriptionConfirmed email
```

### Server Action Mutation Flow (Clean Architecture)

```text
Client form submit
  ↓
Server Action (src/features/[domain]/api/actions.ts)  ← THIN
  1. requireUser()          — verify auth
  2. schema.parse(rawData)  — validate with Zod
  3. callUseCase(data, deps) — delegate to use case
  4. revalidateTag(...)     — invalidate cache
  ↓
Use Case (src/features/[domain]/api/[verb]-[noun].ts)  ← BUSINESS LOGIC
  1. deps.repo.create(...)  — call injected repository
  2. deps.writeAuditLog()   — side effects via injected deps
  3. Return result
  ↓
Repository (src/features/[domain]/lib/[noun].ts)  ← INFRASTRUCTURE
  supabase.from(...).insert(...)
  ↓
Client: catch error → toast.error / toast.success
```

---

## Known Architectural Constraints

- Next.js 16 `params` and `searchParams` are async — always `await` them
- `middleware.ts` is deprecated — use `src/proxy.ts`
- No `tailwind.config.ts` — theme tokens in `globals.css` under `@theme inline`
- `service_role` client must never be imported from client-side code
- Typed routes enabled (`typedRoutes: true`) — route typos fail at compile time
