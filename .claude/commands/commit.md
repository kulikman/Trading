Act as a strict senior engineer and architect for Template Projects.

Prepare a safe commit. Do not push.

Before committing, read:
1. `AGENTS.md`
2. `CLAUDE.md`
3. `ARCHITECTURE.md`
4. `.claude/instincts.md` if present
5. `package.json`

Repository-specific rules:
- This repo uses Next.js 16.2+, React 19.2 and Tailwind v4.
- Do not apply stale Next.js 14/15 assumptions.
- Use `src/proxy.ts`; do not create old `middleware.ts` patterns.
- Follow `ARCHITECTURE.md` and feature public API boundaries.

Workflow:
1. Re-read the previous user request.
2. Run `git status` and inspect the diff.
3. Stage only intentional files. Avoid secrets, generated junk and unrelated changes.
4. Check hallucinations: fake APIs, fake routes, fake env vars, stale framework assumptions, fake completed work.
5. Check boundary drift, broken imports, missing dependencies, dead code, TODOs, security/env leaks and missing UI/error states.
6. Run available checks:
   - `pnpm check`
   - `pnpm verify` for the full local gate
   - `pnpm audit:prod` for production dependency security
   - `pnpm build` for release-sensitive work
   - `pnpm knip` when refactoring/dead-code work is requested
7. Fix issues before committing.
8. Commit only verified meaningful changes using Conventional Commits.

If the user explicitly asks to push:

1. Push only after the local checks above pass.
2. Inspect the GitHub Actions run for the pushed commit.
3. Wait until all required checks complete.
4. If a check fails, fetch the failing logs, fix the cause, commit and push
   again.
5. Report completion only after GitHub checks are successful.

At the end, report:
- commit hash
- commit message
- checks passed
- remaining risks, if any
