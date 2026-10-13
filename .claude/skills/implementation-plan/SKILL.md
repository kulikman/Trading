---
name: implementation-plan
description: Use for multi-step features or refactors before editing code.
---

# Implementation Plan

Act as a senior engineer writing a practical execution plan for a solo founder.

Core rule: plan enough to reduce risk, but do not turn planning into a separate
product.

## When To Use

Use this skill when:

- a task touches multiple files or subsystems;
- acceptance criteria are not obvious;
- work should be split into safe commits;
- tests, docs and migration order matter;
- a future agent or developer may execute the plan later.

Do not use this skill for tiny one-file fixes unless the user explicitly asks
for a plan.

## Workflow

1. Restate the goal in one sentence.
2. Identify the current source of truth files.
3. Map the files likely to change.
4. Split the work into independently verifiable tasks.
5. Define acceptance criteria for each task.
6. List exact verification commands already available in the project.
7. Call out risks, protected files and decisions requiring user approval.

## Plan Quality Rules

- No placeholders like `TBD`, `TODO later` or `add appropriate handling`.
- Do not invent files, commands, routes, env vars or dependencies.
- Each task must end in a visible, testable result.
- Keep scope MVP-first; move nice-to-have work into later tasks.
- If implementation is started immediately, keep the plan short and execute it.

## Output

```markdown
## Implementation Plan: [name]

### Goal
- one sentence

### Source Of Truth
- file or doc

### Tasks
- task with acceptance criteria

### Files Likely To Change
- path and reason

### Verification
- command and what it proves

### Risks
- risk or approval needed
```
