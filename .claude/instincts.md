# Instincts — Architectural Decision Rules

> This file governs HOW architectural decisions are made in this project.
> It's the layer above code style — it answers "what to build" not "how to write it."
> Read this when starting a new feature or facing a structural choice.

---

## Component Architecture

### When to create a new component
- UI element used in 2+ places → extract to `components/[feature]/`
- Component file exceeds 150 lines → split it
- Logic and presentation are tangled → separate them

### When NOT to create a new component
- Used in only one place and under 50 lines → keep it inline
- It's just a styled div → use Tailwind className, not a component

### Component placement
```
One-off, page-specific      → co-locate in app/[route]/
Used across feature         → components/[feature]/
Shared across entire app    → components/ui/ or components/layout/
```

---

## URL Hierarchy & Navigation

### Every route must be navigable at every depth
- Creating `/settings/billing/invoices` means `/settings/billing` and `/settings`
  are also real pages. No dead intermediate URLs.
- Use descriptive nouns: `/projects/[id]`, not `/p/[id]`.
- Route groups `(dashboard)` are for layout, not for URL structure.

### Breadcrumbs are mandatory on nested pages
- Every layout.tsx inside a nested route includes `<Breadcrumbs />`.
- Dynamic slugs → pass `resolveLabel` to show a human title.
- Update `SEGMENT_LABELS` in `breadcrumbs.tsx` for new static routes.
- Update `ROUTES` in `constants.ts` when adding routes.

---

## Data Fetching Architecture

### Server vs Client fetching
- **Default: fetch on the server** (Server Component or API route)
- Move to client only if: real-time updates needed, user-triggered refresh, optimistic UI

### When to use each pattern
```
Static/slow data             → Server Component (async/await directly)
User-specific data           → Server Component with auth check
Real-time (live updates)     → Supabase Realtime subscription (client)
Mutations (create/update)    → Server Action or API route
Heavy server logic           → Supabase Edge Function
```

### Never
- Fetch in Client Component unless real-time is required
- Call Supabase admin client from the browser
- Expose user data without RLS enforcing access

---

## API Design

### Route vs Edge Function decision
```
Auth-protected CRUD          → app/api/ route
Webhook receiver             → Edge Function (verify signature)
3rd-party API call w/secret  → Edge Function
High-frequency / low latency → Edge Function
File processing              → Edge Function with Supabase Storage
```

### API route structure
```ts
// Always: validate input → check auth → execute → return typed response
export async function POST(req: Request) {
  const body = InputSchema.parse(await req.json()); // validate first
  const user = await getAuthUser();                 // auth second
  const result = await doTheWork(body, user);       // logic third
  return Response.json(result);                     // respond last
}
```

---

## Database & Schema

### Before creating a new table
1. Does this data belong in an existing table? → add column instead
2. Is the relationship 1:1? → consider JSONB column first
3. Will this table have user data? → RLS policy is mandatory, write it first

### Migration discipline
- Every schema change → new migration file
- Never edit existing migrations
- Test migration on branch before merging to main

### RLS pattern
```sql
-- Always: enable RLS, then write policies
ALTER TABLE new_table ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only access their own data"
ON new_table FOR ALL
USING (auth.uid() = user_id);
```

---

## State Management

### Decision tree
```
URL state (filters, pagination)  → useSearchParams / router.push
Server state (DB data)           → fetch in Server Component
UI state (modal open, tab)       → useState in Client Component
Cross-component shared state     → Context (small) or Zustand (large)
Form state                       → react-hook-form + Zod
```

### Red flags
- `useState` holding data that came from the server → move fetch to server
- Prop drilling more than 2 levels → introduce Context or restructure
- Multiple `useEffect` chains → extract to a custom hook

---

## Performance Instincts

### Default behavior (always do this)
- Images → next/image with `width` and `height`
- Fonts → next/font (never `<link>` tag)
- Heavy components → dynamic import with `next/dynamic`
- External data → use `"use cache"` directive for opt-in caching (Next 16 pattern)

### When to optimize
- Only optimize after measuring — not by intuition
- Use Vercel Speed Insights or Lighthouse for real data

---

## Security Instincts

### Non-negotiable
- Every table: RLS enabled before any data written
- Every API route: auth checked before any operation
- Every env var with `SERVICE_ROLE`: server-only, never in client bundle
- Every user input: Zod schema before processing

### Watch for
- `"use client"` components that import from `lib/supabase/admin.ts` → NEVER
- API routes without `supabase.auth.getUser()` check → ALWAYS add it
- CORS headers set to `*` on sensitive routes → lock down to specific origins
- Raw `process.env` without going through `src/lib/env.ts` → use `getServerEnv()` / `getClientEnv()`

---

## Error Handling Instincts

### Non-negotiable
- `src/app/error.tsx` exists globally. If a route group (e.g. `(dashboard)`)
  has distinct error UX, add a local `error.tsx` there too.
- `src/app/not-found.tsx` exists with navigation back to home.
- Error boundaries always provide `reset()` retry.

### When to add a local error/loading boundary
- Route group has its own layout (sidebar, nav) → local `error.tsx` + `loading.tsx`
- A page makes a heavy data fetch → local `loading.tsx` with content skeleton
- Default: global boundaries are fine for simple pages

### Error tracking
- Default: `console.error` in `error.tsx`.
- Production: replace with Sentry, LogRocket, or your tracker.
- Always include `error.digest` in user-facing UI for support tickets.

---

## SEO & Metadata Instincts

### Non-negotiable
- Root layout uses `title.template` from `siteConfig` so child pages only set `title`.
- Dynamic pages (`[slug]`) implement `generateMetadata()`.
- `src/app/robots.ts` and `src/app/sitemap.ts` are kept in sync with routes.
- `public/llms.txt` is filled with product info, not template placeholders.

### When to add metadata
- Every public-facing page has `title` + `description`.
- Blog posts / docs add OG image via `generateMetadata()`.
- Dashboard pages behind auth → minimal metadata, no OG.

---

## When to Ask vs When to Proceed

### Ask the owner when
- Feature scope is unclear or could go multiple directions
- A schema change could break existing data
- A new external service/API needs to be integrated (cost implications)
- Security design is ambiguous

### Proceed autonomously when
- Task is clearly scoped in an existing feature
- It's a bug fix with an obvious solution
- It's refactoring that doesn't change behavior
- It's adding tests to existing functionality

---

## Example domain patterns

This template is product-agnostic. When you choose a domain, common patterns include:

### B2B SaaS
- Multi-tenant data → always include `organization_id` in RLS
- Role-based access → store roles in `org_members` table, check in RLS
- Partner portal → separate route group `(partner)/` with own layout
- Usage limits → check `plan_limits` before creating resources

### Fintech / Billing
- Financial amounts → store in smallest unit (cents), display formatted
- Audit trail → add `created_at`, `updated_at`, `created_by` to all tables
- Transactions → immutable records, never UPDATE, only INSERT
- Subscription state → always read from `subscriptions` table, not Stripe directly

### Marketplace / E-commerce
- Orders → immutable after confirmed; use status machine (pending → paid → shipped)
- Inventory → optimistic lock with `version` column to prevent oversell
- Search → full-text search via `tsvector` column or external (Algolia, Typesense)

### Developer Tools / API Products
- API keys → store only SHA-256 hash, show plain key once on creation
- Rate limits → Upstash Redis sliding window per `(user_id, endpoint)`
- Usage metering → dedicated `api_calls` log table; aggregate with cron
