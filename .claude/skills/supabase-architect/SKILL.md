# Skill: /db

## Trigger
`/db [schema, migration, RLS, Supabase, Edge Function task]`

## Purpose
Design and implement the database/security layer for a Supabase-backed product.
This skill is the highest-leverage default for schema work in this template.

## Use when

- designing new tables or relationships
- writing migrations
- adding or reviewing RLS policies
- designing multi-tenant data models
- creating Edge Functions or storage flows

## Process

1. Read `.claude/rules/architecture.md`
2. Read `.claude/rules/data-patterns.md`
3. Read `.claude/rules/security.md`
4. Check current DB types in `src/types/database.ts`
5. Design schema before UI or API

## Output

```
## Database Task: [name]

### Schema
- tables
- columns
- relationships
- indexes

### RLS
- select policy
- insert policy
- update policy
- delete policy

### API / action impact
- server actions
- route handlers
- edge functions

### Files to change
- migration file
- src/types/database.ts
- affected server code

### Risks
- tenancy / auth edge cases
- backfill / existing data risks
```

## Guardrails

- never suggest a table without RLS in the same change
- never trust client-provided `user_id`
- prefer smallest-unit money values for finance/billing
- keep schema changes reversible where possible
