# Patterns — What Works in This Project

> Living document of patterns discovered during development.
> When something works well, document it here so it's reused consistently.
> When something causes problems, document the anti-pattern too.

---

## Established Patterns

### Breadcrumbs on Nested Routes
```tsx
// src/app/docs/layout.tsx
import { Breadcrumbs } from "@/components/layout/breadcrumbs"

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Breadcrumbs className="mb-6" />
      {children}
    </div>
  )
}

// For dynamic segments, resolve slugs to titles:
<Breadcrumbs resolveLabel={(seg) => titleMap[seg] ?? null} />
```

### Supabase Auth Check (Server)
```ts
// Use the server client, then check auth
import { createClient } from '@/lib/supabase/server'

export async function getAuthUser() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) throw new Error('Unauthorized')
  return user
}
```

### API Route Pattern
```ts
export async function POST(req: Request) {
  try {
    const body = InputSchema.parse(await req.json())
    const user = await getAuthUser()
    const result = await processRequest(body, user.id)
    return Response.json({ data: result })
  } catch (error) {
    if (error instanceof ZodError) {
      return Response.json({ error: 'Invalid input' }, { status: 400 })
    }
    return Response.json({ error: 'Internal error' }, { status: 500 })
  }
}
```

### Conditional Tailwind Classes
```ts
import { cn } from '@/lib/utils'

// Use cn() for all conditional class merging
<Button className={cn(
  'base-styles',
  isActive && 'active-styles',
  variant === 'ghost' && 'ghost-styles'
)} />
```

---

## Anti-Patterns (Do Not Use)

### ❌ Fetching in useEffect
```ts
// DON'T — causes waterfall, no streaming, no caching
useEffect(() => {
  fetch('/api/data').then(...)
}, [])

// DO — Server Component with direct async/await
async function Page() {
  const data = await getData()
  return <Component data={data} />
}
```

### ❌ Untyped Supabase queries
```ts
// DON'T — loses type safety
const { data } = await supabase.from('users').select('*')

// DO — explicit column selection + generated types
const { data } = await supabase
  .from('users')
  .select('id, email, created_at')
  .returns<User[]>()
```

---

_Add new patterns as they're discovered_
