# Sync Engine Specification

id: spec/sync-engine
version: 1.0.0

## Purpose

Sync generated agent files into one or many repositories safely.

## Commands

```bash
sfo sync repo <project>
sfo sync all
sfo sync --dry-run
sfo sync --pr
sfo sync --local
```

## Modes

### dry-run

Show what would change without writing.

### local

Write to a local checkout only.

### direct commit

Commit directly to the target repository when explicitly requested.

### pull request

Create a branch and PR for review.

## Safety

Before writing to a target repository:

1. Validate profile.
2. Generate files into a temporary output.
3. Compare current files with generated files.
4. Show diff.
5. Write only controlled SFO blocks unless creating a new file.
6. Never overwrite manual sections.
7. Never write secrets or env values.

## Rollback metadata

Each sync should record:

- batch id
- timestamp
- project
- rule versions
- skill versions
- files changed
- commit hash or PR URL

## Failure behavior

If one repository fails, continue only in dry-run mode. In write mode, stop and report the failing repository.
