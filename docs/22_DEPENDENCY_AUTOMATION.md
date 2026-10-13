# Dependency Automation

Updated: 2026-06-20

Dependency automation is configured through:

```text
renovate.json
```

## Safety Defaults

- Dependency Dashboard is enabled.
- Automerge is not enabled.
- Major updates require dashboard approval.
- Next.js, React, Supabase and Stripe updates require dashboard approval.
- Minor and patch dev dependency updates are grouped.
- PR rate is limited with `prConcurrentLimit` and `prHourlyLimit`.

## Why Renovate

Renovate supports repository-level config files such as `renovate.json` and can
create dependency update pull requests with grouping, scheduling and dashboard
approval.

## Review Rule

Do not merge dependency PRs just because they are automated. For production
framework, auth, database, payment and security packages, inspect release notes
and run the repository checks first.
