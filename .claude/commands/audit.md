Act as a strict senior architect for Template Projects.

Before moving to another large task:

1. Re-read the original user request.
2. Read `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `.claude/instincts.md` if present, and `package.json`.
3. Review the completed work for:
   - hallucinated APIs or routes
   - stale Next.js 14/15 assumptions
   - missing async `params`, `searchParams`, `cookies()`, `headers()` or `draftMode()` handling where applicable
   - accidental `middleware.ts` usage instead of `src/proxy.ts`
   - Tailwind v4/theme drift
   - feature public API boundary drift
   - broken imports
   - missing dependencies
   - incomplete UI states
   - missing error states
   - security/env leaks
   - dead code and TODOs
4. Run checks:
   - `pnpm check`
   - `pnpm verify` when tests are relevant
   - `pnpm build` for release-sensitive work
   - `pnpm knip` when refactoring/dead-code work is requested
5. Fix critical issues.
6. Commit fixes only if needed.
7. Do not push unless the user explicitly asks.

At the end, report:
- completed work status
- fixes made
- checks run
- blockers
- next recommended step
