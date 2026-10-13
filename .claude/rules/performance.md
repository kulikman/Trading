# Rule: Performance

> Applied by: coder, reviewer agents. Required before any PR touching data fetching, rendering, or bundle size.

---

## 1. Eliminate request waterfalls (CRITICAL)

```ts
// ❌ Sequential — each awaits the previous
const user = await getUser(id)
const posts = await getPosts(user.id)
const stats = await getStats(user.id)

// ✅ Parallel — all fire at once
const [user, posts, stats] = await Promise.all([
  getUser(id),
  getPosts(id),
  getStats(id),
])
```

Rule: any two `await` calls that don't depend on each other's result → wrap in `Promise.all`.

---

## 2. Bundle size

- **Direct imports only** — never barrel imports for heavy libs:
  ```ts
  // ❌
  import { format } from "date-fns"   // pulls entire library
  // ✅
  import format from "date-fns/format" // tree-shaken
  ```
- Heavy client components (charts, editors, maps, PDF) → `next/dynamic` with `ssr: false`:
  ```ts
  const Chart = dynamic(() => import("./Chart"), { ssr: false })
  ```
- Run `pnpm build` and check the bundle analyser output before merging large additions.

---

## 3. Rendering strategy

| Data freshness | Strategy |
|---|---|
| Static (docs, pricing) | Server Component, no fetch = build-time |
| Personalised per user | Server Component + `"use cache"` with user tag |
| Real-time (live counts, notifications) | Client Component + Supabase Realtime |
| Slow upstream | `<Suspense>` + streaming |

Never use `useEffect` to fetch data that could be fetched in a Server Component.

---

## 4. Images

Always use `next/image`. Never `<img>` for user-facing content.

```tsx
import Image from "next/image"
<Image src={url} alt="..." width={800} height={600} />
```

- Add `priority` for LCP images (hero, avatars above the fold).
- Use `sizes` prop for responsive images to avoid over-fetching.

---

## 5. React re-renders

```ts
// ❌ Object in dependency array — new ref every render
useEffect(() => { … }, [user])

// ✅ Primitives only
const { id, email } = user
useEffect(() => { … }, [id, email])

// ❌ State that can be derived
const [isAdmin, setIsAdmin] = useState(false)
useEffect(() => setIsAdmin(user.role === "admin"), [user.role])

// ✅ Derive during render
const isAdmin = user.role === "admin"
```

- Non-urgent updates (filter, search) → `useTransition` to avoid blocking the UI.
- Memoize only when profiling proves a problem; don't pre-optimise.

---

## 6. Caching (Next 16 — explicit opt-in)

```ts
// Cache a slow function for 60 seconds
export async function getProducts() {
  "use cache"
  cacheLife("minutes")           // built-in profile: 60s client / 300s server
  return supabase.from("products").select("*")
}

// Cache per user
export async function getUserDashboard(userId: string) {
  "use cache"
  cacheTag(`user-${userId}`)
  return fetchDashboardData(userId)
}

// Invalidate from a Server Action
revalidateTag(`user-${userId}`)
```

Do NOT use `fetch` cache options (`next: { revalidate }`) for Supabase calls —
those don't pass through the fetch layer. Use `"use cache"` instead.

---

## 7. Core Web Vitals checklist

Before marking a PR as ready:
- [ ] No waterfalls (Promise.all for independent fetches)
- [ ] LCP image has `priority`
- [ ] No layout shift (explicit width/height on media)
- [ ] Heavy components are dynamically imported
- [ ] No `useEffect` data fetch that could move to Server Component
