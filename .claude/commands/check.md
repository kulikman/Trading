Act as a strict senior engineer and architect for Template Projects.

Do not commit. Do not push.

Before working, read:
1. `AGENTS.md`
2. `CLAUDE.md`
3. `ARCHITECTURE.md`
4. `.claude/instincts.md` if present
5. `package.json`
6. `.claude/skills/verification/SKILL.md`

Repository-specific rules:
- This repo uses Next.js 16.2+, React 19.2 and Tailwind v4.
- Do not apply stale Next.js 14/15 assumptions.
- Dynamic route `params`, `searchParams`, `cookies()`, `headers()` and `draftMode()` are async in Next.js 16.
- Use `src/proxy.ts`; do not create old `middleware.ts` patterns.
- Tailwind theme lives in `src/app/globals.css` under `@theme`.
- Follow `ARCHITECTURE.md` and feature public API boundaries.

Tasks:
1. Re-read the user request.
2. Inspect relevant files before editing.
3. Check hallucinations: fake APIs, fake routes, fake env vars, stale framework assumptions, fake completed work.
4. Check broken imports, missing dependencies, boundary drift, dead code, TODOs, security/env leaks and missing UI/error states.
5. Run available checks:
   - `pnpm check`
   - `pnpm verify` when tests are relevant
   - `pnpm build` for release-sensitive work
   - `pnpm knip` when refactoring/dead-code work is requested
6. Fix only necessary issues.
7. Do not claim success unless the verification evidence from this session supports it.

At the end, report:
- what was checked
- what was fixed
- checks run
- remaining risks
- whether it is ready for commit
