# Skill: /review

## Trigger
`/review` — run a code quality check on current or specified file/feature

## Purpose
Quality gate before committing or opening a PR. Checks against the rules
defined in CLAUDE.md and `.claude/instincts.md`.

## Review Checklist

### TypeScript
- [ ] No `any` type anywhere
- [ ] No `@ts-ignore` comments
- [ ] All functions have explicit return types
- [ ] External data validated with Zod
- [ ] Interfaces used for object shapes

### Security
- [ ] No secrets hardcoded
- [ ] No `service_role` key in client components
- [ ] All API routes check auth before operating
- [ ] All new tables have RLS enabled + policies written

### React
- [ ] No class components
- [ ] Named exports only (no default exports)
- [ ] Components under 150 lines
- [ ] `"use client"` only where actually needed
- [ ] No data fetching in useEffect (use Server Components)

### Supabase
- [ ] RLS enabled on all new tables
- [ ] TypeScript types match current schema
- [ ] Migrations written for schema changes
- [ ] Admin client not used on client side

### Styling
- [ ] Tailwind only (no inline styles)
- [ ] `cn()` used for conditional classes
- [ ] Mobile-first responsive design

### Code Quality
- [ ] No duplicated logic (DRY)
- [ ] Error handling on all async operations
- [ ] No `console.log` in production paths
- [ ] Absolute imports with `@/` prefix

## Output Format

```
## Code Review: [file or feature]

### ✅ Passing
- [item]

### ❌ Issues Found
- [issue] → [fix]

### ⚠️ Warnings
- [item to watch]

### Summary
[overall assessment + recommended actions]
```

## Quick Commands
- `/review src/app/api/route.ts` — review specific file
- `/review auth` — review auth feature
- `/review` — review currently open/discussed code
