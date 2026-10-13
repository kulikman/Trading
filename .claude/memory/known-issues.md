# Known Issues & Workarounds

> Document bugs, gotchas, and non-obvious behaviour found during development.

---

## posthog-js peer dep warning with React 19

**Symptom:** `pnpm install` prints a peer dependency warning for posthog-js.
**Cause:** posthog-js declares peer dep on React `^18` but React 19 is installed.
**Workaround:** Add to `pnpm-workspace.yaml` `onlyBuiltDependencies` or use:
```bash
pnpm install --ignore-peer-deps
```
PostHog works correctly at runtime with React 19.

---

## Supabase Realtime: missing auth in anon channels

**Symptom:** Realtime channel receives no events even though data exists.
**Cause:** RLS blocks realtime if the row's `user_id` doesn't match the connected session.
**Fix:** Always add a filter to channels:
```ts
.on("postgres_changes", {
  filter: `user_id=eq.${userId}`,
  ...
})
```
And ensure `alter publication supabase_realtime add table public.your_table` is in the migration.

---

## next/font + Turbopack in dev

**Symptom:** Fonts flash unstyled on first load in dev (not production).
**Cause:** Turbopack doesn't cache font subsets the same way webpack does in dev.
**Status:** Known Next.js Turbopack issue. No workaround needed — production builds are fine.

---

## Stripe webhook: 400 on local dev

**Symptom:** Stripe webhook handler returns 400 "No signatures found matching the expected signature".
**Cause:** `await request.text()` must be called before `stripe.webhooks.constructEvent()`. Using `await request.json()` corrupts the raw body.
**Fix:**
```ts
const body = await request.text()  // NOT request.json()
const event = stripe.webhooks.constructEvent(body, sig, secret)
```

---

## `params` must be awaited in Next.js 16

**Symptom:** TypeScript error: "Property 'id' does not exist on type 'Promise<{id: string}>'".
**Cause:** Dynamic route params are async in Next.js 16.
**Fix:**
```tsx
// ✅
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
}
```

---

## `middleware.ts` no longer works in Next.js 16

**Symptom:** Session not refreshed, security headers missing.
**Cause:** `middleware.ts` is deprecated in Next.js 16.
**Fix:** Use `src/proxy.ts` (already done in this project). Never create `middleware.ts`.

---

## Zod 4: `.optional()` on env vars

**Symptom:** Optional env vars throw validation errors even when intentionally unset.
**Cause:** Zod 4 changed `.optional()` behaviour — `undefined` passes, but empty string `""` fails a `.url()` validator.
**Fix:** Use `.optional().or(z.literal(""))` for env vars that may be set to empty string in CI:
```ts
RESEND_API_KEY: z.string().optional().or(z.literal(""))
```
