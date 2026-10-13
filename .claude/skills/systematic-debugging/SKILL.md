---
name: systematic-debugging
description: Use for bugs, failing tests, build errors, runtime errors, regressions, and unexpected behavior.
---

# Systematic Debugging

Act as a repro-first debugging engineer.

Core rule: find the root cause before patching symptoms.

Do not make random fixes. Do not bundle multiple speculative changes. If the
cause is unclear, gather more evidence before editing.

## Workflow

1. Read the exact error message, stack trace or failing assertion.
2. Reproduce the issue with the smallest command or manual path.
3. Inspect recent changes and nearby working examples.
4. Trace the failing value or behavior to its source.
5. State one hypothesis and the evidence for it.
6. Make the smallest fix that addresses the source.
7. Add or update a regression test when practical.
8. Run focused verification, then broader checks if the fix is credible.

## Stop Conditions

Pause and reassess if:

- reproduction is not understood;
- three attempted fixes fail;
- the fix requires broad architecture changes;
- the observed behavior conflicts with project documentation;
- the issue touches auth, billing, secrets, payments or production data.

## Good Debugging Habits

- Prefer expected vs actual wording.
- Keep one variable changing at a time.
- Compare broken code with the closest working pattern in this repo.
- Fix the source of the bad data, not only the crash site.
- Leave a regression test or a clear reason why one was not added.

## Output

```markdown
## Debug Report

### Expected
- expected behavior

### Actual
- actual behavior

### Reproduction
- command or steps

### Root Cause
- cause and evidence

### Fix
- smallest safe change

### Regression Test
- added test or reason not added

### Checks
- command: result
```
