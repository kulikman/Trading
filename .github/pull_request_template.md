## Summary

What changes and why. One sentence.

## Type

- [ ] feat — new user-facing capability
- [ ] fix — bug fix
- [ ] refactor — internal cleanup, no behavior change
- [ ] chore — tooling, deps, CI
- [ ] docs

## Checklist

- [ ] `pnpm verify` passes locally
- [ ] New env vars added to `src/lib/env.ts` AND `.env.example`
- [ ] New tables ship with RLS policies in the same migration
- [ ] New routes registered in `ROUTES` and `SEGMENT_LABELS` if nested
- [ ] No `any`, no raw `process.env`, no new `middleware.ts`
- [ ] Breadcrumbs render on every nested route deeper than `/dashboard`
