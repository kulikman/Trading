# Agent Policy Source

Updated: 2026-06-20

`Template-Projects` is the canonical source for Solo Founder Agent OS policy
files. The policy source lives under `solo-founder-os/` and is versioned by
`.agent-policy-version`.

## Current Version

```text
1.0.0
```

The detailed source map is stored in:

```text
solo-founder-os/policy/manifest.yml
```

## What Is Canonical

- Core rules: `solo-founder-os/core/*.md`
- Stack rules: `solo-founder-os/stacks/*.md`
- Domain rules: `solo-founder-os/domains/*.md`
- Skills: `solo-founder-os/skills/*.yml`
- Project profiles: `solo-founder-os/project-profiles/*.yml`
- Policy packs: `solo-founder-os/policy/packs/*.yml`
- Output templates: `solo-founder-os/templates/*`
- Generator, history and sync specs: `solo-founder-os/specs/*.md`

## What Is Not Automated Yet

- No cross-repo sync action is configured yet.
- No GitHub PR fan-out is configured yet.
- No generated repo dashboard exists yet.
- No anti-hallucination checker exists yet beyond the current SFO validation
  and test suite.

These belong to the next epics.

## Rollout Rule

Policy changes should move to other repositories through reviewable diffs.
The default rollout mode is pull request, not direct push.

Before applying policy to a target repository:

1. Audit the target repository stack and existing agent files.
2. Select the matching policy pack.
3. Generate files from `solo-founder-os`.
4. Inspect the diff.
5. Run the target repository checks that actually exist.
6. Commit only intentional files.

## Policy Packs

The manifest currently declares these initial packs:

- `next16`
- `next15`
- `flutter`
- `backend-docker`
- `hono-mcp`
- `static-site`
- `finance-risk`
- `crm-production`

The pack files live under `solo-founder-os/policy/packs/`. They are metadata
only for now. They do not imply that generated repo files are already updated.
