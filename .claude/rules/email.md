# Rule: Email

> Applied by: coder agent. Read before any email sending, template creation, or transactional flow.

Stack: **Resend HTTP API via `fetch`** + plain HTML templates in
`src/lib/email/templates.ts`.

Do not assume the `resend`, `react-email`, or `@react-email/components`
packages are installed. Add those dependencies only after an explicit product
decision.

---

## 1. When to send emails

| Trigger | Email type | Priority |
|---|---|---|
| User signs up | Welcome + verify email | Transactional (immediate) |
| Password reset requested | Reset link | Transactional (immediate) |
| Subscription upgraded | Receipt + confirmation | Transactional (immediate) |
| Subscription cancelled | Cancellation confirmation | Transactional (immediate) |
| Payment failed | Dunning email | Transactional (immediate) |
| Weekly summary | Digest | Batch (scheduled cron) |
| Re-engagement (30d inactive) | Nudge | Marketing (opt-in only) |

Never send marketing emails to users who haven't explicitly opted in.

---

## 2. Sending from Server Actions / Route Handlers

```ts
// src/lib/email/index.ts
import "server-only"
import { getServerEnv } from "@/lib/env"

export async function sendEmail(params: {
  to: string
  subject: string
  html: string
  text?: string
}): Promise<{ ok: true; dryRun?: boolean } | { ok: false; error: string }> {
  const env = getServerEnv()

  if (!env.RESEND_API_KEY || !env.RESEND_FROM_EMAIL) {
    return { ok: true, dryRun: true }
  }

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.RESEND_FROM_EMAIL,
      to: params.to,
      subject: params.subject,
      html: params.html,
      text: params.text,
    }),
  })

  if (!response.ok) {
    return { ok: false, error: `Resend ${response.status}` }
  }

  return { ok: true }
}
```

---

## 3. Plain HTML template pattern

```ts
// src/lib/email/templates.ts
export function welcomeEmail(input: { name: string; appUrl: string }): {
  subject: string
  html: string
  text: string
} {
  return {
    subject: "Welcome",
    html: `<p>Welcome, ${input.name}. Open ${input.appUrl} to get started.</p>`,
    text: `Welcome, ${input.name}. Open ${input.appUrl} to get started.`,
  }
}
```

---

## 4. Rate limiting outbound emails

Never fire emails in a tight loop (e.g. bulk import). Use a queue pattern:

```ts
// For bulk sends — add to a queue, process via cron
// src/app/api/cron/send-digests/route.ts
import { after } from "next/server"

export async function GET(request: Request) {
  // Verify CRON_SECRET
  const authHeader = request.headers.get("authorization")
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return Response.json({ error: "Unauthorized" }, { status: 401 })
  }

  // Fetch users due for digest — process in batches of 50
  // Use after() so the response returns immediately
  after(async () => {
    const batch = await getUsersForDigest()
    for (const user of batch) {
      await sendEmail({ to: user.email, subject: "Your weekly digest", html: renderDigestHtml(user) })
      await new Promise(r => setTimeout(r, 100)) // 100ms between sends
    }
  })

  return Response.json({ ok: true })
}
```

---

## 5. Rules

- `RESEND_FROM_EMAIL` must be a verified domain in Resend — never send from gmail/yahoo
- Always validate recipient email before sending (Zod `.email()`)
- Unsubscribe links are required for marketing emails — use Resend's list management
- Never log email bodies — they may contain PII
- Preview emails locally only after adding a real preview script to `package.json`
- Test with real addresses on staging — Resend's sandbox mode catches issues early
