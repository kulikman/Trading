# Security Policy

## Supported Versions

Only the latest version on `main` receives security patches.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately:

1. Go to **Security → Advisories → Report a vulnerability** in this repository.
2. Or email: **security@2skymobile.com** (replace with your address before using this template).

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected versions / components
- Any suggested fix (optional but appreciated)

We aim to acknowledge reports within **48 hours** and provide a remediation timeline within **7 days**.

## Scope

| In scope | Out of scope |
|----------|-------------|
| Authentication bypass | Third-party services (Supabase, Vercel, Stripe) |
| Authorization flaws | Rate-limit circumvention without exploitable impact |
| Data exposure via API | Social engineering |
| XSS / CSRF vulnerabilities | Spam or DoS |
| RLS policy bypasses | Issues in test/staging environments |

## Disclosure Policy

We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
We ask that you give us a reasonable time to remediate before public disclosure.

## Security Hardening Notes

This template ships with the following security measures:

- **Content-Security-Policy** — set in `src/lib/security-headers.ts` and applied via `src/proxy.ts`
- **HSTS** — `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- **Rate limiting** — `src/lib/rate-limit.ts` (swap with Upstash for multi-region production)
- **CSRF protection** — validate `Origin` header in all Server Actions
- **Zod validation** — all external inputs validated at the boundary (`src/lib/env.ts`, feature schemas)
- **Supabase RLS** — Row-Level Security enabled on all tables; `service_role` key is server-only
- **Dependency scanning** — Gitleaks + `pnpm audit` run on every CI push
- **CodeQL** — JavaScript/TypeScript security analysis runs on pushes, PRs and weekly schedule
