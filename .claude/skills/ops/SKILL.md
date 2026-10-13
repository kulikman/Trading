# Skill: /ops

## Trigger
`/ops [weekly review, backlog cleanup, risk review, founder ops task]`

## Purpose
Keep a solo-founder project operationally clear: what shipped, what is stuck,
what matters next, and what should be removed or deferred.

## Use when

- doing weekly review
- cleaning backlog
- updating project memory
- reviewing risks and blockers
- deciding the next three tasks
- preparing handoff notes

## Process

1. Read `docs/09_CURRENT_STATUS.md`
2. Read `docs/08_BACKLOG.md`
3. Read `.claude/memory/project-state.md`
4. Inspect recent git history when relevant
5. Separate confirmed progress from assumptions

## Output

```
## Ops Review

### Shipped
- item

### Stuck
- item

### Risks
- item

### Cleanup
- item

### Next 3 Tasks
1. task
2. task
3. task
```

## Guardrails

- never invent completed work
- keep the next tasks concrete and small
- prefer deleting or deferring low-value work over carrying it forever
- update memory only with confirmed facts
