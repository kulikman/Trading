# Agent Policy Rollout

Updated: 2026-06-20

This document defines how to roll out Template-Projects agent policy changes to
other repositories.

## Rollout Stages

1. Update policy source in `Template-Projects`.
2. Run `pnpm verify`.
3. Run `pnpm agent:inventory`.
4. Run `pnpm agent:status`.
5. Review `docs/21_AGENT_POLICY_STATUS.md`.
6. Run the `Agent Policy Sync` workflow with `dry_run: true`.
7. Run the workflow with `dry_run: false`, `repo` or `limit`, and
   `watch_checks: true` for the first wave.
8. Review and merge generated PRs repository by repository after checks pass.
9. Repeat with the next wave only after the previous wave is clean.

## First Wave

Use a small wave before syncing all active targets:

- `kulikman/open-design-kit`
- `kulikman/kulikov-world`
- `kulikman/neosim-mobile`

These repositories cover static/unknown, lightweight site and Flutter-style
policy cases without starting from the most production-sensitive repos.

## Production-Sensitive Repositories

Review these manually before merge:

- `kulikman/2Skymobile-CRM`
- `kulikman/2Skymobile-web`
- `kulikman/Founder-OS`
- `kulikman/Secret-project`
- `kulikman/elaurion-finance`
- `kulikman/theta-aurion`

## PR Review Checklist

- Confirm the PR only changes files listed in `.github/agent-policy-sync.yml`.
- Confirm `.agent-policy-version` matches `Template-Projects`.
- Confirm no `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.cursor/` or workflow files
  were changed by the sync PR.
- Run target repository checks that actually exist.
- Inspect protected areas if the target repo has custom protected paths.
- Merge only after checks pass or the failure is understood and accepted.

## PR Engine

The PR-only propagation engine is:

```bash
pnpm agent:sync-pr -- --apply --repo kulikman/open-design-kit --watch-checks
```

It creates or reuses `agent-policy-sync/<policy-version>` branches in target
repositories, opens pull requests and waits for checks when `--watch-checks` is
set. It must not push directly to target `main` branches.

## Rollback

If a policy sync PR is wrong:

1. Close the PR.
2. Fix the source policy in `Template-Projects`.
3. Run `pnpm verify`.
4. Re-run sync in dry-run mode.
5. Re-open sync PRs only after the diff is correct.

Do not force-push target repositories to undo policy sync. Use normal revert
commits if a bad sync was already merged.

## Labels

Sync PRs should carry:

- `agent-policy-sync`
- `automated-pr`

These labels are configured in `.github/workflows/agent-policy-sync.yml`.
