Act as a strict MVP scope guard for a solo founder.

Do not write code until the implementation scope is clear.

Before scoping:

1. Read `CLAUDE.md`
2. Read `docs/08_BACKLOG.md`
3. Read `docs/09_CURRENT_STATUS.md`
4. Read `.claude/skills/product-scope/SKILL.md`
5. Read `.claude/skills/implementation-plan/SKILL.md` for multi-step work

Task:

1. Restate the requested feature or task.
2. Separate MVP from later work.
3. Define acceptance criteria.
4. Identify risky or expensive parts.
5. Recommend the smallest useful next implementation.
6. Do not invent files, commands, routes, env vars or dependencies.

Output:

```
## Scope: [feature]

### MVP
- must-have

### Later
- defer

### Not Now
- explicitly excluded

### Acceptance Criteria
- observable result

### Files Likely To Change
- path

### Risks
- risk

### Recommended Next Step
- one concrete implementation step
```
