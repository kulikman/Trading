Act as a repro-first debugging engineer.

Do not patch symptoms. Find the smallest root-cause fix.

Before fixing:

1. Read `CLAUDE.md`
2. Read `.claude/memory/mistakes.md`
3. Read `.claude/skills/systematic-debugging/SKILL.md`
4. Inspect the failing code and nearby tests

Task:

1. Write the bug in expected vs actual form.
2. Identify reproduction steps.
3. Find the root cause.
4. Propose the smallest safe fix.
5. Add or update a regression test when practical.
6. Run relevant checks.
7. Do not attempt broad refactors until the root cause is proven.

Output:

```
## Bug Report: [title]

### Expected
- expected behavior

### Actual
- actual behavior

### Reproduction
1. step

### Root Cause
- cause

### Fix
- changed behavior

### Regression Test
- test added or reason not added

### Checks
- command: result
```
