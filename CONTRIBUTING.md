# Contributing

Quick reference for outside contributors and freelancers picking up
work on this repo. The full stack rules live in [`CLAUDE.md`](CLAUDE.md);
the architecture / module-isolation rules live in
[`ARCHITECTURE.md`](ARCHITECTURE.md). Read both before opening a PR.

## One-time setup

```bash
nvm use                # pins Node 20 from .nvmrc
corepack enable        # uses the pnpm version pinned in package.json
pnpm install
cp .env.example .env.local && fill in Supabase keys
pnpm dev
```

## Daily loop

```bash
pnpm dev                 # localhost:3000 (Turbopack)
pnpm verify              # typecheck + lint + tests — run before every PR
pnpm format              # auto-format with Prettier
```

Pre-commit hook (Husky + lint-staged) runs `eslint --fix` and Prettier
on staged files automatically.

## Pull request expectations

- One logical change per PR. If your branch touches more than one
  feature module, split it (see ARCHITECTURE.md §6).
- All four CI jobs must pass: `quality`, `test`, `secrets-scan`,
  `dependency-audit`, and `build`.
- Conventional Commits in commit messages (`feat:`, `fix:`, `chore:`,
  `refactor:`, `docs:`, `test:`).
- New tables: include the migration **and** RLS policies in the same
  file (see [`supabase/migrations/0001_init_profiles.sql`](supabase/migrations/0001_init_profiles.sql)).
- New env vars: add to `src/lib/env.ts` schema **and** `.env.example`
  in the same commit.
- New routes: add to `ROUTES` (`src/lib/constants.ts`) and to
  `src/config/routes.ts` if nested, public, or linked from navigation.

## Forbidden in this repo

- `any` (use `unknown` and narrow)
- `process.env.X` direct access (go through `getServerEnv()` /
  `getClientEnv()`; ESLint will block you)
- New `middleware.ts` (use `src/proxy.ts` — Next 16 convention)
- Default exports outside `app/`, `proxy.ts`, and error boundaries
- Tables without RLS policies in the same migration

## Reporting issues

Use the templates under `.github/ISSUE_TEMPLATE/`. Always include:
the version of `next`, the reproduction steps, and the relevant log
lines (`logger` outputs JSON — paste raw).
