Act as a strict senior engineer and architect for Template Projects.

Prepare safe commit and push only if the user explicitly asked to push/ship/deploy.

Before acting, read:
1. `AGENTS.md`
2. `CLAUDE.md`
3. `ARCHITECTURE.md`
4. `.claude/instincts.md` if present
5. `package.json`
6. `.claude/skills/verification/SKILL.md`

Repository-specific rules:
- This repo uses Next.js 16.2+, React 19.2 and Tailwind v4.
- Do not apply stale Next.js 14/15 assumptions.
- Use `src/proxy.ts`; do not create old `middleware.ts` patterns.
- Follow `ARCHITECTURE.md` and feature public API boundaries.

Workflow:
1. Re-read the previous user request.
2. Run `git status` and inspect the diff.
3. Check hallucinations, fake APIs, fake routes, fake env vars, stale framework assumptions, dead code and broken dependencies.
4. Check boundary drift and UI/error state completeness.
5. Run available checks:
   - `pnpm check`
   - `pnpm verify` when tests are relevant
   - `pnpm build` before push/release-sensitive work
   - `pnpm knip` when refactoring/dead-code work is requested
6. Fix issues if needed.
7. Commit verified changes.
8. Push only after checks pass and only when explicitly requested.
9. Never claim shipped, pushed, passing or ready without fresh verification evidence.

At the end, report:
- branch
- commit hash
- commit message
- push result
- checks passed
- remaining risks, if any
