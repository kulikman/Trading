# Generator Specification

id: spec/generator
version: 1.0.0

## Purpose

Generate agent-facing files from layered project profiles.

## Inputs

- core rules
- stack rules
- domain rules
- skills
- project profile
- project overrides

## Outputs

```text
AGENTS.md
CLAUDE.md
.cursor/rules/agent-workflow.mdc
.claude/commands/check.md
.claude/commands/save-work.md
.claude/commands/release-work.md
.claude/commands/review-work.md
.codex/instructions.md
```

## Controlled blocks

The generator must update only marked blocks.

```md
<!-- SFO:BEGIN core/git-protocol@1.0.0 -->

...

<!-- SFO:END core/git-protocol@1.0.0 -->
```

Manual sections outside SFO blocks must never be overwritten.

## Merge order

1. core
2. stack
3. domain
4. skills
5. project overrides

Later layers may add specificity, but must not silently contradict earlier layers.

## Validation before generation

- all referenced rules exist
- all referenced skills exist
- stack compatibility is valid
- skill compatibility is valid
- forbidden conflicts are not present
- output paths are allowed

## Failure behavior

If validation fails, generation must stop and report the conflict.
