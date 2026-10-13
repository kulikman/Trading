# Agent Policy Validation

Updated: 2026-06-20

Agent policy validation is handled by:

```text
pnpm agent:policy-check
```

The check is also part of:

```text
pnpm verify
```

## What It Checks

- `.agent-policy-version` matches `solo-founder-os/policy/manifest.yml`.
- Manifest source paths exist.
- Policy pack references point to real core, stack, domain and skill files.
- Project profile inheritance references real files.
- Skill `requires` references real files.
- Agent policy sync source paths exist.
- Agent policy sync target repositories are present in the generated inventory
  when `docs/18_AGENT_REPO_INVENTORY.md` exists.
- Project profile `overrides.checks` commands exist in the target repository
  `package.json` when they use `pnpm <script>`.
- Project profile stack inheritance matches generated inventory stack signals
  for Next.js and Flutter profiles.
- Project profile forbidden paths do not exist in the target checkout when the
  forbidden value looks like a path.
- Project profile protected paths are reported as warnings when they are not
  present in the target checkout.

## What It Does Not Check Yet

- It does not parse YAML with a full YAML parser.
- It does not inspect remote GitHub repositories live.
- It does not validate generated `AGENTS.md` or `CLAUDE.md` content in target
  repositories.
- It does not prove that target repository commands pass.
- Hono/MCP detection depends on generated inventory stack signals from local
  package files.

Those belong to later sync and rollout epics.
