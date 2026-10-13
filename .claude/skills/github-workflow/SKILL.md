# Skill: /ci

## Trigger
`/ci [workflow, GitHub Actions, release, branch protection, automation task]`

## Purpose
Design or update CI/CD and repository automation in a way that matches the
existing scripts and guardrails of this template.

## Use when

- adding GitHub Actions workflows
- tightening PR checks
- wiring release automation
- adding secrets scanning or dependency audit checks

## Process

1. Read `package.json` and existing `.github/workflows/*`
2. Use only commands that actually exist in the repo
3. Prefer simple pipelines over wide matrix complexity
4. Keep required checks aligned with `pnpm check`, `pnpm verify`, and `pnpm build`

## Output

```
## CI Task: [name]

### Goal
- what the workflow should protect

### Jobs
- job name
- command
- trigger

### Required secrets / env
- variable
- why it is needed

### Risks
- flaky step
- expensive step

### Verification
- how to test locally
- how to validate in GitHub
```

## Guardrails

- do not invent scripts that are missing from `package.json`
- do not weaken branch protection without an explicit reason
- keep build, typecheck, lint, and tests visible as separate concerns
