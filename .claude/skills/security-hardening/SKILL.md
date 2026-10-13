# Skill: /security

## Trigger
`/security [auth, headers, webhook, secret, RLS, rate limit task]`

## Purpose
Apply focused security hardening to the current repository without drifting into
generic advice.

## Use when

- auditing auth or authorization flows
- checking env and secret handling
- hardening webhooks, cron routes, uploads, or API handlers
- reviewing CSP, proxy, or rate-limiting changes

## Process

1. Read `.claude/rules/security.md`
2. Read `.claude/rules/code-style.md`
3. Inspect the exact files in scope before proposing changes
4. Classify issues by severity
5. Prefer the smallest safe fix first

## Output

```
## Security Task: [scope]

### Critical
- issue
- concrete fix

### High Risk
- issue
- concrete fix

### Medium / Low
- issue
- follow-up

### Files to inspect or change
- path

### Verification
- checks to run
```

## Guardrails

- never move `service_role` logic into client code
- always re-check `supabase.auth.getUser()` usage on protected flows
- never recommend disabling security headers for convenience
- prefer explicit verification steps over “looks safe”
