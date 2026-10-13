# Product Decisions

> Why things are the way they are. Read before proposing architectural changes.

---

## Auth: Supabase Auth (not NextAuth / Clerk)

**Decision:** Use Supabase Auth.
**Reason:** We already depend on Supabase for the database and storage. Adding a second auth provider (Clerk/NextAuth) would duplicate user management and add a monthly cost with no benefit for solo/small-team SaaS.
**Trade-off:** Less OAuth provider choice out of the box; mitigated by Supabase's built-in providers (Google, GitHub, Apple, etc.).

---

## Session refresh: proxy.ts (not middleware.ts)

**Decision:** Session refresh lives in `src/proxy.ts`, not `middleware.ts`.
**Reason:** Next.js 16 deprecated `middleware.ts`. `proxy.ts` runs on Node.js by default, avoids the Edge runtime restrictions (no `fs`, no `child_process`), and is the blessed pattern going forward.
**Do not revert** to `middleware.ts`.

---

## Payments: Stripe (not Paddle / LemonSqueezy)

**Decision:** Stripe for billing.
**Reason:** Best-in-class developer API, widest global coverage, most resources and examples. Stripe's complexity is worth it for anything beyond hobby projects.
**Trade-off:** More setup work (webhook handler, product/price configuration). Consider LemonSqueezy if you need merchant of record (tax handling) without extra code.

---

## Validation: Zod 4 (not Valibot / Yup)

**Decision:** Zod 4 for all input validation.
**Reason:** Team familiarity, excellent TypeScript inference, wide ecosystem support. Zod 4 added `.parse()` performance improvements that make it viable in hot paths.
**Rule:** All external data (form inputs, API payloads, env vars) goes through `.safeParse()` or `.parse()` before touching the database.

---

## Styling: Tailwind v4 + shadcn/ui (not CSS Modules / styled-components)

**Decision:** Tailwind v4 with PostCSS plugin + shadcn/ui primitives.
**Reason:** Tailwind v4 removes the config file, improves build performance (Oxide engine), and co-locates styles with markup. shadcn/ui gives unstyled accessible primitives without a runtime CSS-in-JS cost.
**Rule:** No `tailwind.config.ts`. Theme lives in `globals.css` via `@theme`. No `@apply` — it's deprecated in v4.

---

## Caching: opt-in "use cache" (not automatic)

**Decision:** Next.js 16 removed implicit fetch caching. All caching is explicit via `"use cache"` directive.
**Reason:** Implicit caching was the #1 source of stale-data bugs in Next.js 13-15. Explicit is better.
**Rule:** Never assume data is cached. Add `"use cache"` + `cacheTag()` + `cacheLife()` deliberately.

---

## Module architecture: bounded feature modules

**Decision:** `src/features/[domain]/` with `index.ts` public barrel, enforced by `eslint-plugin-boundaries`.
**Reason:** Prevents spaghetti imports as the codebase grows. Each feature is independently deployable in the future if needed.
**Rule:** One table = one owning feature. Cross-feature calls via barrel only.
