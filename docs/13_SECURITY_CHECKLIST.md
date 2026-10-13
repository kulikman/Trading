# Security Checklist

> Run this checklist before every production deployment and after adding new features.
> Each item that doesn't apply should be marked N/A with a reason.

---

## Authentication

- [ ] Auth validated on backend via `supabase.auth.getUser()` (not `getSession()`)
- [ ] All protected routes guarded in `proxy.ts`
- [ ] Session expiry handled — expired sessions redirect to `/login`
- [ ] Invalid tokens rejected (Supabase handles this)
- [ ] OAuth provider payloads verified (Supabase handles this)
- [ ] Password reset flow works and links expire after use

---

## Authorization (RLS)

- [ ] RLS enabled on **every** table (`ALTER TABLE x ENABLE ROW LEVEL SECURITY`)
- [ ] Users cannot read other users' data (verified with test user)
- [ ] Admin routes check `profiles.role IN ('admin', 'super_admin')` on backend
- [ ] Server Actions call `supabase.auth.getUser()` before any DB operation
- [ ] `service_role` client (`lib/supabase/admin.ts`) never imported from `"use client"` files
- [ ] Org-scoped data cannot be accessed by non-members

---

## Input Validation

- [ ] All Server Action inputs validated with Zod before DB operations
- [ ] All Route Handler request bodies validated with Zod
- [ ] Query params validated (especially IDs used in DB queries)
- [ ] File uploads: type and size validated before Supabase Storage upload
- [ ] Frontend validation is UX-only — never sole security check

---

## Secrets & Environment

- [ ] No secrets in source code (check with `grep -r "sk_live\|sk_test\|SUPABASE_SERVICE" src/`)
- [ ] No secrets in client bundle (check `pnpm build` for warnings)
- [ ] `.env.local` in `.gitignore` ✅
- [ ] `.env.example` has all required vars documented ✅
- [ ] `src/lib/env.ts` validates all env vars at startup ✅
- [ ] Server env accessed via `getServerEnv()`, client env via `getClientEnv()`

---

## Payments (Stripe)

- [ ] Webhook signature verified via `stripe.webhooks.constructEvent()`
- [ ] Payment status comes from Stripe webhook, not from client payload
- [ ] Duplicate webhooks handled idempotently (upsert, not insert)
- [ ] Failed payments trigger user notification
- [ ] Stripe keys: `sk_test_*` on staging, `sk_live_*` on production only

---

## API Keys (if enabled)

- [ ] Only SHA-256 hash stored — plain key shown once at creation
- [ ] `verifyApiKey()` used on every public API endpoint
- [ ] API key usage logged (`last_used_at` updated)
- [ ] Users can revoke their own keys

---

## Admin Panel (when built)

- [ ] Admin routes protected: `role IN ('admin', 'super_admin')` check on every Server Action
- [ ] Destructive admin actions require confirmation dialog
- [ ] All admin actions written to `audit_logs` table
- [ ] Admin cannot access other admins' credentials

---

## HTTP Security

- [ ] Security headers set in `proxy.ts` (CSP, HSTS, X-Frame-Options, etc.) ✅
- [ ] CORS not set to `*` on sensitive endpoints
- [ ] CRON_SECRET required for cron endpoints ✅
- [ ] Rate limiting on auth endpoints (Supabase built-in or add upstash)

---

## Logging

- [ ] Critical errors logged with `console.error` (or Sentry if configured)
- [ ] No sensitive data logged (passwords, tokens, full PII)
- [ ] Admin actions logged to `audit_logs`
- [ ] Payment events logged
- [ ] Auth failures logged (Supabase handles this)

---

## Dependencies

- [ ] `pnpm audit` passes (run in CI) ✅
- [ ] `next` pinned to 16.2.4+ (CVE-2025-66478 patched) ✅
- [ ] No packages with known critical CVEs
