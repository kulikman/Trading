# API Contracts

## Architecture Note

This project uses **Server Actions** for most mutations — not REST endpoints.
Route Handlers (`app/api/`) are used only for:
- Stripe webhooks (external callback)
- Cron jobs (Vercel scheduled functions)
- Public API endpoints (when `NEXT_PUBLIC_FF_API_KEYS=true`)

---

## Response Format (Route Handlers)

Success:
```json
{ "ok": true, "data": {} }
```

Error:
```json
{ "ok": false, "error": "Human-readable message" }
```

---

## Server Actions (mutations)

Server Actions throw on error. Clients catch with try/catch + toast.
All actions require authentication (`supabase.auth.getUser()`).
All inputs validated with Zod before DB operations.

### Pattern

```ts
// src/features/[domain]/api/actions.ts
"use server"

export async function createItemAction(rawData: unknown): Promise<void> {
  const supabase = await createServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  const { name } = schema.parse(rawData)   // throws ZodError on invalid input

  const { error } = await supabase.from("items").insert({ name, user_id: user.id })
  if (error) throw new Error(error.message)

  revalidateTag(`items:${user.id}`)
}
```

---

## Webhook: POST /api/webhooks/stripe

**Auth:** Stripe-Signature header (HMAC verification via `stripe.webhooks.constructEvent`)

### Handled Events

| Event | Action |
|---|---|
| `checkout.session.completed` | upsertSubscription, send confirmation email |
| `customer.subscription.updated` | upsertSubscription |
| `customer.subscription.deleted` | upsertSubscription (status → canceled) |
| `invoice.payment_failed` | send payment_failed email |

### Response
```json
{ "received": true }
```

---

## Cron: GET /api/cron/cleanup

**Auth:** `Authorization: Bearer ${CRON_SECRET}` header

**Schedule:** Daily at 03:00 UTC (configured in `vercel.json`)

**Actions:**
- DELETE notifications where `read_at < now() - 30 days`
- DELETE org_members where `expires_at < now() AND accepted_at IS NULL`

**Response:**
```json
{ "ok": true, "deleted": { "notifications": 12, "expiredInvites": 3 } }
```

---

## Public API (optional, feature-flagged)

Enabled when `NEXT_PUBLIC_FF_API_KEYS=true`.
Authenticated via `x-api-key` header (SHA-256 hash lookup in `api_keys` table).

### GET /api/v1/[resource]

**Auth:** `x-api-key: [api-key]`

**Response:**
```json
{
  "ok": true,
  "data": { "items": [], "pagination": { "cursor": "...", "hasMore": false } }
}
```

**Errors:**
```json
{ "ok": false, "error": "Unauthorized" }      // 401
{ "ok": false, "error": "Not found" }          // 404
{ "ok": false, "error": "Validation failed" }  // 422
{ "ok": false, "error": "Rate limited" }       // 429
```

### Verify API Key (pattern)

```ts
import { verifyApiKey } from "@/features/api-keys"

export async function GET(request: Request) {
  const userId = await verifyApiKey(request.headers.get("x-api-key"))
  if (!userId) return Response.json({ ok: false, error: "Unauthorized" }, { status: 401 })
  // ... handle request
}
```

---

## Updating Contracts

> **Rule:** Do not change API response shapes or Server Action signatures without updating this file.

When adding a new Route Handler or changing an existing one:
1. Document it here (method, path, auth, request, response, errors)
2. Update `src/lib/constants.ts` if adding a new route
3. Write or update tests in `*.test.ts` colocated with the handler
