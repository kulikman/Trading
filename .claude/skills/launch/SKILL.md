# Skill: /launch

## Trigger
`/launch [release, deploy, go-live, production readiness request]`

## Purpose
Prepare a solo-founder SaaS product for launch without missing boring but
expensive details.

## Use when

- preparing a production release
- checking readiness before a public launch
- validating auth, payments, emails, SEO, analytics, and deployment
- deciding whether a build is safe to ship

## Process

1. Read `AGENTS.md`
2. Read `CLAUDE.md`
3. Read `package.json`
4. Read `docs/09_CURRENT_STATUS.md`
5. Inspect deployment, auth, payment, email, SEO, analytics, and error-handling files
6. Run available checks before saying the project is ready

## Output

```
## Launch Readiness

### Ready
- item

### Blockers
- item and fix

### Warnings
- item and follow-up

### Checks
- command: result

### Verdict
Ready / Not ready
```

## Guardrails

- never claim launch readiness without running relevant checks
- never skip env, auth, payment, webhook, or email validation
- keep deferred launch work explicit
- do not invent integrations or dashboards that are not configured
