# SFO CLI

Minimal CLI for Solo Founder Agent OS.

## Commands

```bash
pnpm sfo:list
pnpm sfo:status
pnpm sfo:status neosim-web
pnpm sfo:validate
pnpm sfo:validate neosim-web
pnpm sfo:generate neosim-web
pnpm sfo:write-local neosim-web
pnpm sfo:merge-local neosim-web
pnpm sfo:dry-run
pnpm sfo:snapshot neosim-web
pnpm sfo:history
```

## Current status

This is the first safe MVP skeleton.

It can:

- list project profiles
- show connected rule/skill versions with `sfo status`
- validate references to core, stack, domain and skill files
- detect conflicting `next15` + `next16` stack usage
- generate concrete agent files from templates to stdout
- write generated files into `.sfo-generated/<project>/`
- merge only controlled SFO blocks into `.sfo-merged/<project>/`
- perform a dry-run summary
- save snapshot metadata into `.sfo-history/<project>/`
- show snapshot history for all projects or one project

It does not write to other repositories yet.

## Version/status view

```bash
pnpm sfo:status neosim-web
```

Shows which rule and skill versions a profile uses:

```text
neosim-web
repo: kulikman/neosim-web
profile status: draft
core:
  - core/git-protocol@1.0.0
stacks:
  - stack/next16@1.0.0
```

## Safe local generation

```bash
pnpm sfo:write-local neosim-web
```

Writes generated files to:

```text
.sfo-generated/neosim-web/
```

This allows reviewing generated `AGENTS.md`, `CLAUDE.md`, Cursor rules and Claude commands before syncing them into real repositories.

## Controlled-block merge

```bash
pnpm sfo:merge-local neosim-web
```

Reads existing generated files from:

```text
.sfo-generated/neosim-web/
```

Writes merged files to:

```text
.sfo-merged/neosim-web/
```

The merge updates only blocks like:

```md
<!-- SFO:BEGIN core/git-protocol@1.0.0 -->
...
<!-- SFO:END core/git-protocol@1.0.0 -->
```

Manual content outside SFO blocks is preserved.

## Snapshot history

```bash
pnpm sfo:snapshot neosim-web
pnpm sfo:history
pnpm sfo:history neosim-web
```

`sfo snapshot` creates metadata only. It does not restore files and it does not
overwrite manual sections.

Snapshot manifests are written to:

```text
.sfo-history/<project>/<batch-id>.json
```

Each manifest stores at least:

- batch id
- project
- repo
- timestamp
- command
- generated files list
- referenced rule versions

Example:

```json
{
  "batchId": "2026-06-19T10-00-00-000Z-a1b2c3d4",
  "project": "neosim-web",
  "repo": "kulikman/neosim-web",
  "profileStatus": "draft",
  "timestamp": "2026-06-19T10:00:00.000Z",
  "command": "snapshot",
  "generatedFiles": [
    { "path": "AGENTS.md", "bytes": 2048 }
  ],
  "ruleVersions": [
    "core/git-protocol@1.0.0",
    "stack/next16@1.0.0"
  ]
}
```

`sfo history` lists saved entries grouped by project and sorted newest-first.

## Next steps

1. Add real YAML parser or keep strict internal YAML subset.
2. Add GitHub sync via PR mode.
3. Add restore/rollback flow on top of snapshot metadata.
4. Add agent behavior tests.
