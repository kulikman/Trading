# AGENTS.md — Stack Warning for AI Agents

> Read this **before** writing any code in this repo.

## This is Next.js 16, not Next.js 14

If your training data is from early 2025 or before, it describes **Next.js 14 or
15**. This repo uses **Next.js 16.2+** with **React 19.2** and **Tailwind v4**.
Do not apply older patterns blindly.

### Breaking changes you will otherwise get wrong

1. **`params` and `searchParams` are `Promise<...>`, not plain objects.** `await` them.
2. **`middleware.ts` is deprecated → use `src/proxy.ts`.** Node.js runtime, not Edge. Default or named `proxy` export.
3. **Caching is opt-in.** Use `"use cache"` directive. No implicit memoization.
4. **No `tailwind.config.ts`.** Theme lives in `src/app/globals.css` under `@theme`.
5. **`next/image` `domains` removed** — use `remotePatterns` in `next.config.ts`.
6. **Turbopack is default** for `next dev` and `next build`.
7. **`cookies()`, `headers()`, `draftMode()` are async.**

### Use `CLAUDE.md` as the authoritative stack reference

For full rules (style, Supabase, security, pre-commit) → read `CLAUDE.md`.
For module boundaries and feature public APIs → read `ARCHITECTURE.md`.
For architectural decisions → read `.claude/instincts.md`.
For session state → read `.claude/memory/project-state.md`.

## Git Safety Rules

Before commit:

1. Run `git status`
2. Inspect the diff
3. Run all applicable checks
4. Fix failures before commit
5. Stage only intentional files

Never:

- `git add .`
- `git add -A`
- `git push --force`
- `--no-verify`

Push only if the user explicitly requested push.

After push:

1. Check the GitHub Actions run for the pushed commit.
2. Watch until every required GitHub check finishes.
3. If any check fails, inspect logs, fix the cause, commit and push again.
4. Do not report the task as complete while GitHub checks are failing or still
   pending.

## Verification

Run all applicable checks before commit.

Preferred commands in this repo:

- `pnpm check`
- `pnpm verify`
- `pnpm audit:prod`
- `pnpm build` for release-sensitive work

Do not claim a fix works unless the relevant checks were actually run.

## Anti-Hallucination Rules

Never invent:

- APIs
- routes
- database columns
- environment variables
- services
- external integrations
- completed work

If a contract, file, command, or integration is missing, say so explicitly and
work from the real codebase instead of assumptions.

## Protected Files And Sensitive Areas

Ask before editing these paths or flows unless the task explicitly targets them:

- `supabase/migrations/**`
- `src/lib/supabase/admin.ts`
- `src/proxy.ts`
- `src/types/database.ts`
- `src/app/api/webhooks/stripe/**`
- `src/app/auth/callback/**`

Do not weaken auth, RLS, billing, webhook, or session-refresh logic for
convenience.

### When in doubt

Run `cat node_modules/next/package.json | grep version` to confirm the installed
major. Read `node_modules/next/dist/esm/lib/...` or `https://nextjs.org/docs` for
the current API. **Do not invent APIs from memory.**
