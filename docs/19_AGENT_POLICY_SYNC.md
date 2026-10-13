# Agent Policy Sync

Updated: 2026-06-20

This repo contains a manual PR-only sync workflow for the canonical Solo
Founder Agent OS policy bundle.

## Workflow

```text
.github/workflows/agent-policy-sync.yml
```

The workflow is `workflow_dispatch` only. It does not run automatically on every
push.

Default mode is dry-run:

```text
dry_run: true
```

`dry_run: false` runs the PR-only propagation engine. It creates or updates
sync branches in target repositories, opens pull requests and can wait for PR
checks.

Useful workflow inputs:

- `repo`: optional single target, for example `kulikman/open-design-kit`
- `limit`: optional maximum number of targets
- `watch_checks`: wait for PR checks before finishing the workflow

## Local Dry Run

```text
pnpm agent:sync-dry-run
```

The local dry run reads `.github/agent-policy-sync.yml` and
`docs/18_AGENT_REPO_INVENTORY.md`, then compares canonical policy bundle files
against local repository checkouts.

## PR Sync Engine

```bash
pnpm agent:sync-pr -- --dry-run
pnpm agent:sync-pr -- --apply --repo kulikman/open-design-kit --watch-checks
pnpm agent:sync-pr -- --apply --limit 3 --watch-checks
```

The engine uses `gh` and `git` to:

1. Clone each target repository into a temporary directory.
2. Create or reuse a branch named `agent-policy-sync/<policy-version>`.
3. Copy only the canonical bundle paths listed in `.github/agent-policy-sync.yml`.
4. Refuse unexpected changed files outside the allowed sync mappings.
5. Commit and push the sync branch.
6. Create or reuse a pull request.
7. Optionally wait for PR checks with `gh pr checks --watch --fail-fast`.

## Sync Config

```text
.github/agent-policy-sync.yml
```

The config plans sync for only canonical policy bundle files:

- `.agent-policy-version`
- `solo-founder-os/core/`
- `solo-founder-os/stacks/`
- `solo-founder-os/domains/`
- `solo-founder-os/skills/`
- `solo-founder-os/policy/`
- `solo-founder-os/project-profiles/`
- `solo-founder-os/templates/`
- `solo-founder-os/specs/`

It does not sync live repository files such as `AGENTS.md`, `CLAUDE.md`,
`.claude/`, `.cursor/` or `.github/workflows/`. Those files can contain
repo-specific manual sections and need a safer generated-block workflow before
automatic updates.

## Required Secret For Future Write Sync

Write sync requires a repository secret:

```text
GH_PAT
```

Cross-repository write access requires a personal access token. The default
`GITHUB_TOKEN` is not enough for creating branches and pull requests in other
repositories.

## Safety Rules

- Keep `dry_run: true` for plan-only runs.
- Use `dry_run: false` only when you are ready to create or update target PRs.
- Prefer `repo` or `limit` for the first wave before syncing all active targets.
- Do not add `AGENTS.md`, `CLAUDE.md`, `.claude/` or `.cursor/` to this sync
  config until generated-block merging exists.
- Exclude archived and miscellaneous local-only repositories from the active
  sync target list.
