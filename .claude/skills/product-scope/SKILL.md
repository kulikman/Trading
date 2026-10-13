# Skill: /scope

## Trigger
`/scope [feature, product idea, backlog item, implementation request]`

## Purpose
Protect a solo founder from scope creep by turning a broad idea into the
smallest useful implementation that can be built, tested, and shipped.

## Use when

- a feature request feels too broad
- a task has unclear acceptance criteria
- a product idea mixes MVP, later work, and nice-to-haves
- a technical implementation is about to expand beyond the original goal

## Process

1. Restate the user goal.
2. Separate MVP, later, and not-now work.
3. Define acceptance criteria that can be observed.
4. Identify risky or expensive assumptions.
5. Recommend one smallest next implementation.

## Output

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

### Risks
- risk

### Recommended Next Step
- one concrete step
```

## Guardrails

- never hide deferred work inside vague wording
- never define success as "looks good" without observable behavior
- prefer a working vertical slice over broad partial infrastructure
- call out when a requested feature needs a decision before implementation
