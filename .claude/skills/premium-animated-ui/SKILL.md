# Skill: /ui

## Trigger
`/ui [page, component, flow, redesign request]`

## Purpose
Create polished product UI that still respects the architecture and component
boundaries of this template.

## Use when

- building landing sections
- creating dashboard components
- designing onboarding or pricing flows
- improving visual hierarchy without changing product logic

## Process

1. Read `.claude/rules/architecture.md`
2. Read `.claude/rules/code-style.md`
3. Check whether the work belongs in `src/components/ui/`, `src/components/`,
   or a feature folder
4. Keep data flow separate from presentation
5. Prefer intentional motion and hierarchy over generic styling

## Output

```
## UI Task: [name]

### User goal
- what the interface should help the user do

### Component plan
- server components
- client components
- shared primitives

### Visual direction
- layout
- typography
- motion
- states

### Files to change
- path

### Verification
- desktop checks
- mobile checks
- accessibility checks
```

## Guardrails

- preserve existing design-system patterns when already established
- do not add visual complexity that hides product clarity
- keep forms, errors, empty states, and loading states explicit
