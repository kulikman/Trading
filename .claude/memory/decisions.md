# Architectural Decisions Log

> Permanent record of significant decisions made during this project.
> When a decision is made, log it here so future sessions don't re-debate it.
> Format: most recent at top.

---

## Template

```
### [Date] — [Decision Title]
**Context:** Why this decision was needed
**Decision:** What was decided
**Alternatives Considered:** What was rejected and why
**Consequences:** What this means going forward
```

---

## Decisions

### 2026-04 — Stack Pinning to Next.js 16
**Context:** Project is Template-Projects (fork of the SaaS template stack)
**Decision:** Next.js 16 App Router + React 19.2 + Supabase + Tailwind v4 + shadcn/ui v4 + Vercel
**Alternatives Considered:** Remix (less ecosystem), Prisma (redundant with Supabase types), Next.js 14/15 (EOL path)
**Consequences:** All data fetching in Server Components by default; `proxy.ts` replaces `middleware.ts`; `"use cache"` for opt-in caching; Edge Functions for sensitive ops

---

_Add new decisions above this line_
