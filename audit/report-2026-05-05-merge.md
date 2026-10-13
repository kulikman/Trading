# Audit Report — 2026-05-05 (post-merge)

## Summary

Repository is in a **healthy, merge-safe state**: ESLint, TypeScript, unit tests, and `next build` pass after a small set of compatibility fixes.
The main issue found was **build-time prerendering of auth-gated routes** which required Supabase env vars; this was fixed by switching root metadata to `getPublicMetadataEnv()` and marking the Settings route group as `dynamic = "force-dynamic"`.

## Compatibility checks (local)

- `pnpm lint`: pass
- `pnpm tsc --noEmit`: pass
- `pnpm test`: pass
- `pnpm build`: pass (without Supabase env)

## Rule status table

| Rule ID | Severity | Status | Comment |
|---|---:|---:|---|
| SEC-001 | CRITICAL | pass | No hardcoded secrets detected; CI runs gitleaks; workflow placeholders are neutral. |
| SEC-002 | CRITICAL | pass | `createAdminClient` usage is server-only; no client imports of `@/lib/supabase/admin`. |
| SEC-003 | CRITICAL | pass | Logging uses `logger`; no tokens/keys printed. |
| SEC-004 | CRITICAL | pass | Protected APIs use `requireUser()`; public endpoints are explicitly documented (`/api/health`), webhooks use signature verification. |
| TS-001 | HIGH | pass | `tsc --noEmit` passes; no `any` usage found in source. |
| TS-002 | MEDIUM | pass | Exported handlers/utilities consistently declare return types. |
| TS-003 | HIGH | pass | Route handlers validate inputs via Zod (`safeParse`). |
| NEXT-001 | CRITICAL | pass | No private env access from `"use client"` components; env access is centralized in `src/lib/env.ts`. |
| NEXT-002 | MEDIUM | pass | Client components are used where needed (Header, error boundaries, theme toggle). |
| NEXT-003 | HIGH | pass | IO paths return proper errors; error boundaries exist. |
| SB-001 | MEDIUM | pass | `src/types/database.ts` exists; migrations are tracked in `supabase/migrations/*`. |
| SB-002 | HIGH | pass | Server code uses server/admin clients; client code does not import server-only clients. |
| SB-003 | CRITICAL | pass | No key/token leakage in logs; webhook errors redact secrets. |
| REACT-001 | MEDIUM | pass | List rendering uses stable keys (e.g. `href`) in nav. |
| REACT-002 | HIGH | pass | Hooks usage is conventional; lint passes. |
| REACT-003 | LOW | pass | Components use named exports per repo convention. |
| UI-001 | MEDIUM | pass | No raw hex colors found in `src/components`. |
| UI-002 | HIGH | pass | Navigation and buttons have accessible labels; focus/semantics via shadcn primitives. |
| UI-003 | LOW | pass | No layout-property animations detected in recent changes. |
| PERF-001 | MEDIUM | pass | No obvious heavy client-only deps in critical UI; analytics are flag-gated. |
| PERF-002 | MEDIUM | pass | No raw `<img>` usage found in `src/`. |
| TEST-001 | MEDIUM | pass | Critical utilities and validations have tests; test suite green. |
| CI-001 | HIGH | pass | CI runs lint + typecheck + format + tests + build + gitleaks + audits. |
| CI-002 | MEDIUM | na | Requires GitHub branch protection settings verification (out of repo scope). |
| OBS-001 | HIGH | pass | No empty `catch {}` blocks; errors are logged or rethrown with context. |
| OBS-002 | MEDIUM | pass | No `console.log` in runtime source (only docs/examples). |
| API-001 | MEDIUM | pass | Route handlers return consistent 4xx/5xx without leaking internals. |
| API-002 | HIGH | pass | Stripe webhook handler is idempotent via upsert; critical POSTs validate input. |
| ARCH-001 | MEDIUM | pass | No client components import server-only modules. |
| ARCH-002 | LOW | pass | Core logic is placed in `src/lib/*` / `src/hooks/*`. |
| DOC-001 | LOW | pass | README covers setup, env, and key scripts. |
| PKG-001 | LOW | pass | Lockfile exists; pnpm is pinned via `packageManager`. |
| LEGAL-001 | HIGH | pass | PII footprint is minimal (profiles + email flows); no extra sensitive fields stored by default. |
| UX-001 | HIGH | pass | Nested protected routes render `<Breadcrumbs />` in their layouts. |
| UX-002 | MEDIUM | pass | URL hierarchy maintained for current nested routes (`/settings`, `/settings/billing`). |
| SEO-001 | LOW | fail | `public/llms.txt` still contains template placeholder copy; should be replaced with real product info. |
| ERR-001 | HIGH | pass | Global `app/error.tsx` exists; route-group boundaries exist for `dashboard/` and `settings/`. |
| ERR-002 | MEDIUM | pass | `app/not-found.tsx` exists and links back home. |
| ENV-001 | HIGH | pass | Zod env validation in `src/lib/env.ts` (server + client + public metadata). |
| SEO-002 | MEDIUM | pass | Root metadata uses `siteConfig` title template; dynamic metadata conventions are documented. |
| SEO-003 | LOW | pass | `robots.ts` and `sitemap.ts` are implemented and read validated public metadata env. |
| SEC-005 | HIGH | pass | Protected layouts call `requireUser()` (`dashboard`, `settings`). |
| METADATA-001 | MEDIUM | pass | Root `metadataBase` reads from `getPublicMetadataEnv()` (no Supabase keys required). |
| A11Y-002 | LOW | pass | Header closes mobile menu on route change (pathname tracking). |
| CSP-001 | MEDIUM | pass | Security headers centralized in `src/proxy.ts` + `src/lib/security-headers.ts`. |
| TEST-002 | LOW | pass | Zod schemas have unit coverage in `src/lib/validations.test.ts`. |

## CRITICAL / HIGH items (priority)

- (none) — all CRITICAL/HIGH rules are currently passing.

## Notes / fixes applied during this audit

- Root layout now reads `metadataBase` via `getPublicMetadataEnv()` to avoid requiring Supabase env keys during build.
- Settings route group is explicitly `dynamic = "force-dynamic"` to prevent build-time prerender of auth-gated pages.
- Added `src/app/settings/error.tsx` so Settings has its own error boundary per ERR-001.

