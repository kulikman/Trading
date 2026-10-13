# Quick Recipes

> Copy-paste patterns for common tasks. Verified against the project stack.

---

## Add a new feature module

```bash
mkdir -p src/features/[name]/{components,lib,api}
touch src/features/[name]/index.ts
touch src/features/[name]/api/actions.ts
touch supabase/migrations/000X_[name].sql
```

Checklist:
- [ ] `index.ts` exports only the public API
- [ ] Migration has RLS + policies
- [ ] `tsconfig.json` alias added: `"@/features/[name]": ["./src/features/[name]/index.ts"]`

---

## Add a new DB table (migration template)

```sql
-- 000X_feature_name.sql
create table if not exists public.table_name (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null check (char_length(name) between 1 and 128),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists table_name_user_idx on public.table_name(user_id);

create trigger table_name_set_updated_at
  before update on public.table_name
  for each row execute function public.set_updated_at();

alter table public.table_name enable row level security;

create policy "Users can read own rows"
  on public.table_name for select to authenticated
  using (auth.uid() = user_id);

create policy "Users can insert own rows"
  on public.table_name for insert to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update own rows"
  on public.table_name for update to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "Users can delete own rows"
  on public.table_name for delete to authenticated
  using (auth.uid() = user_id);
```

---

## Protect a route (auth gate in Server Component)

```tsx
import { redirect } from "next/navigation"
import { createServerClient } from "@/lib/supabase/server"

export default async function ProtectedPage() {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  // rest of page...
}
```

---

## Server Action template

```ts
"use server"

import { revalidateTag } from "next/cache"
import { redirect } from "next/navigation"
import { z } from "zod"
import { createServerClient } from "@/lib/supabase/server"

const schema = z.object({
  name: z.string().min(1).max(128),
})

export async function createItem(formData: FormData) {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  const { name } = schema.parse({ name: formData.get("name") })

  const { error } = await supabase.from("items").insert({ name, user_id: user.id })
  if (error) throw new Error(error.message)

  revalidateTag(`items:${user.id}`)
}
```

---

## Send a notification from a Server Action

```ts
import { sendNotification } from "@/features/notifications"

await sendNotification(userId, {
  title: "Payment received",
  body: "Your Pro subscription is now active.",
  kind: "success",
  href: "/settings/billing",
})
```

---

## Gate a feature by plan

```tsx
import { createServerClient } from "@/lib/supabase/server"
import { getPlanLimits } from "@/lib/plan-limits"
import { PlanGate } from "@/components/plan-gate"

export default async function AiPage() {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()

  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("product_id")
    .eq("user_id", user!.id)
    .eq("status", "active")
    .maybeSingle()

  const limits = getPlanLimits(subscription?.product_id)

  return (
    <PlanGate allowed={limits.aiEnabled} feature="AI Assistant">
      <AiChatPanel />
    </PlanGate>
  )
}
```

---

## Track a server-side event

```ts
import { trackServerEvent } from "@/lib/analytics"

await trackServerEvent("subscription_upgraded", user.id, {
  from_plan: "free",
  to_plan: "pro",
  revenue: 12,
})
```

---

## Verify API key in a Route Handler

```ts
import { verifyApiKey } from "@/features/api-keys"

export async function POST(request: Request) {
  const userId = await verifyApiKey(request.headers.get("x-api-key"))
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 })

  // handle request...
}
```

---

## Add a cron job

1. Add route handler: `src/app/api/cron/[job-name]/route.ts`
2. Verify secret in the handler:
   ```ts
   const auth = request.headers.get("authorization")
   if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
     return Response.json({ error: "Unauthorized" }, { status: 401 })
   }
   ```
3. Register in `vercel.json`:
   ```json
   { "crons": [{ "path": "/api/cron/[job-name]", "schedule": "0 9 * * 1" }] }
   ```
