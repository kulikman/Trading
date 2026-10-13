# Rule: Data Patterns

> Applied by: coder, architect agents. Read before writing any data fetching, mutations, or pagination.

---

## 1. Server Actions (mutations)

All mutations go through Server Actions — never raw `fetch` to your own API from client components.

```ts
// src/features/[domain]/api/actions.ts
"use server"

import { revalidateTag } from "next/cache"
import { redirect } from "next/navigation"
import { createServerClient } from "@/lib/supabase/server"
import { z } from "zod"

const schema = z.object({ name: z.string().min(1).max(64) })

export async function createItem(rawData: unknown) {
  // 1. Auth check
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  // 2. Validate
  const { name } = schema.parse(rawData)

  // 3. Mutate
  const { error } = await supabase.from("items").insert({ name, user_id: user.id })
  if (error) throw new Error(error.message)

  // 4. Invalidate
  revalidateTag(`items:${user.id}`)
}
```

Rules:
- Always validate with Zod before writing to the DB
- Always call `supabase.auth.getUser()` — never trust client-passed user IDs
- Throw on error (the calling component handles it with try/catch + toast)
- Invalidate relevant cache tags after mutation

---

## 2. Optimistic updates (React 19)

Use `useOptimistic` for instant feedback on lists:

```tsx
"use client"
import { useOptimistic, useTransition } from "react"
import { deleteItem } from "./actions"

export function ItemList({ items }: { items: Item[] }) {
  const [optimisticItems, removeOptimistic] = useOptimistic(
    items,
    (state, idToRemove: string) => state.filter(i => i.id !== idToRemove)
  )
  const [, startTransition] = useTransition()

  function handleDelete(id: string) {
    startTransition(async () => {
      removeOptimistic(id)           // instant UI update
      await deleteItem(id)           // actual server call
      // On error: React automatically rolls back to `items` prop
    })
  }

  return optimisticItems.map(item => (
    <div key={item.id}>
      {item.name}
      <button onClick={() => handleDelete(item.id)}>Delete</button>
    </div>
  ))
}
```

---

## 3. Cursor-based pagination (scales; use instead of OFFSET)

```ts
// Server Component or Server Action
export async function getItems(cursor?: string, limit = 20) {
  const supabase = await createServerClient()

  let query = supabase
    .from("items")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit + 1)   // +1 to detect if there's a next page

  if (cursor) {
    query = query.lt("created_at", cursor)
  }

  const { data } = await query
  const hasMore = (data?.length ?? 0) > limit
  const items = hasMore ? data!.slice(0, limit) : (data ?? [])
  const nextCursor = hasMore ? items[items.length - 1].created_at : null

  return { items, nextCursor, hasMore }
}
```

Never use OFFSET pagination for user-facing lists — it's slow and produces
duplicate/missing rows when data is inserted between page loads.

---

## 4. Real-time subscriptions

```tsx
"use client"
import { useEffect, useState } from "react"
import { createBrowserClient } from "@/lib/supabase/client"

export function LiveList({ initial }: { initial: Item[] }) {
  const [items, setItems] = useState(initial)

  useEffect(() => {
    const supabase = createBrowserClient()
    const channel = supabase
      .channel("items-live")
      .on("postgres_changes", {
        event: "*",
        schema: "public",
        table: "items",
      }, (payload) => {
        if (payload.eventType === "INSERT") {
          setItems(prev => [payload.new as Item, ...prev])
        }
        if (payload.eventType === "DELETE") {
          setItems(prev => prev.filter(i => i.id !== payload.old.id))
        }
      })
      .subscribe()

    return () => { void supabase.removeChannel(channel) }
  }, [])

  return items.map(item => <div key={item.id}>{item.name}</div>)
}
```

Rules:
- Always clean up channels in the `useEffect` return function
- Seed `useState` with server-fetched initial data to avoid flash of empty state
- Add `filter: "user_id=eq.${userId}"` to channels where data is user-scoped

---

## 5. Error handling in Server Actions

```ts
// In the Server Action — throw typed errors
export async function createItem(data: unknown) {
  // ...
  if (error) throw new Error(error.message)
}

// In the client component — catch and show toast
"use client"
import { toast } from "sonner"

function handleSubmit() {
  startTransition(async () => {
    try {
      await createItem(formData)
      toast.success("Item created!")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Something went wrong.")
    }
  })
}
```

---

## 6. File uploads

Always use Supabase Storage, never store files in the DB.

```ts
// Server Action
export async function uploadFile(formData: FormData) {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error("Unauthorized")

  const file = formData.get("file") as File
  if (!file) throw new Error("No file provided")

  // Validate type and size
  const ALLOWED = ["image/jpeg", "image/png", "image/webp"]
  if (!ALLOWED.includes(file.type)) throw new Error("Invalid file type")
  if (file.size > 5 * 1024 * 1024) throw new Error("File too large (max 5 MB)")

  const path = `${user.id}/${crypto.randomUUID()}.${file.name.split(".").pop()}`
  const { error } = await supabase.storage.from("uploads").upload(path, file)
  if (error) throw new Error(error.message)

  const { data: { publicUrl } } = supabase.storage.from("uploads").getPublicUrl(path)
  return publicUrl
}
```
