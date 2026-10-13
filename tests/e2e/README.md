# E2E tests

Playwright is already wired into this template. The default e2e run starts the
app with placeholder Supabase env values so UI smoke tests can run without a
real backend.

```bash
pnpm exec playwright install
pnpm test:e2e
```

Backend-dependent scenarios are skipped unless a real test backend is provided.
Use one of these when validating a concrete project created from the template:

```bash
TEST_BASE_URL=http://localhost:3000 pnpm test:e2e
E2E_USE_REAL_SUPABASE=1 pnpm test:e2e
```

Keep the real Supabase test project isolated from production. Do not point e2e
tests at a shared template database.

## What to cover first

The 80/20 of E2E for this template:

1. **Login flow** — happy path + invalid credentials
2. **Protected route redirect** — visiting `/dashboard` while signed out
   redirects to `/login`
3. **Theme persistence** — toggle theme, reload, verify class on `<html>`

Skip exhaustive UI coverage — Vitest already covers utilities and pure
logic; Playwright should only chase the bugs that only a real browser
can find (auth cookies, redirects, hydration).
