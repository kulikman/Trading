# Snapshot History Specification

id: spec/history-manifest
version: 1.0.0

## Purpose

Record rollback-friendly metadata for generated SFO outputs without restoring or
rewriting repository files.

## Location

```text
.sfo-history/<project>/<batch-id>.json
```

## Commands

```bash
sfo snapshot [project]
sfo history [project]
```

## Snapshot manifest fields

Each manifest must include at least:

- `batchId`
- `project`
- `repo`
- `profileStatus`
- `timestamp`
- `command`
- `generatedFiles`
- `ruleVersions`

## Generated files entry

Each `generatedFiles` item stores:

- `path`
- `bytes`

## Safety

- Snapshot metadata must not overwrite manual sections.
- Snapshot metadata must not restore files in this MVP.
- Invalid profiles must be reported and skipped.

## Future extension

This format is designed to support later rollback work by adding:

- sync mode
- commit hash or PR URL
- changed-files diff metadata
- restore eligibility flags
