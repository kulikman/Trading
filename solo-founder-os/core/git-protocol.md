# Git Protocol

id: core/git-protocol
version: 1.0.0
applies_to: all

## Purpose

Make every agent follow a safe and predictable git workflow.

## Before commit

1. Run `git status`.
2. Inspect the diff.
3. Re-read the user request.
4. Check that changed files match the requested work.
5. Run all applicable project checks.
6. Fix failures before committing.
7. Stage only intentional files.

## Never do

- Do not use `git add .`.
- Do not use `git add -A`.
- Do not use `--no-verify`.
- Do not force-push to main or production branches.
- Do not commit `.env*`, secrets, private keys, DB dumps, logs with sensitive data or generated credentials.

## Commit message

Use Conventional Commits:

```text
feat:
fix:
refactor:
chore:
docs:
test:
perf:
ci:
```

Prefer a clear lowercase subject.

## Push rule

Push only when the user explicitly asks to push, ship, release or deploy.

## Report after git work

Return:

- branch
- commit hash
- commit message
- checks run
- push result, if any
- remaining risks
