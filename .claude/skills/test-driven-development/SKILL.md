---
name: test-driven-development
description: Use when implementing behavior changes, bug fixes, regressions, and refactors where tests are practical.
---

# Test-Driven Development

Act as a behavior-first engineer.

Core rule: prove the test can fail before trusting it.

## When To Use

Use this skill for:

- new behavior;
- bug fixes;
- regression coverage;
- refactors with observable behavior;
- CLI, parser, validation, data and workflow logic.

For pure docs, config-only changes or generated files, use verification instead.

## Red Green Refactor

1. Write one minimal failing test for the desired behavior.
2. Run the focused test and confirm it fails for the expected reason.
3. Implement the smallest code change that makes it pass.
4. Run the focused test again and confirm it passes.
5. Refactor only after green.
6. Run broader checks before reporting success.

## Test Quality Rules

- Test behavior, not implementation details.
- Use clear names that describe the expected outcome.
- Prefer real code paths over mocks unless external systems make that unsafe.
- Split tests when the name needs `and`.
- Do not weaken or delete failing tests to make the suite pass.

## Output

```markdown
## TDD Report

### Behavior
- behavior under test

### Red
- command and expected failure

### Green
- command and passing result

### Refactor
- cleanup or none

### Broader Checks
- command: result
```
