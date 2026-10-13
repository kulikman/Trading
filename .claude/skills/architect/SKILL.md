# Skill: /architect

## Trigger
`/architect [feature or system description]`

## Purpose
System design advisor. Given a feature description, output:
- Data model (tables, columns, relationships)
- API shape (routes or Edge Functions)
- Component tree (what to build, where it lives)
- RLS policies needed
- Potential risks or edge cases

## Process

1. **Understand the feature**
   - What does the user see?
   - What data is created/read/updated/deleted?
   - Who has access to what?

2. **Design the data model first**
   - List tables needed
   - Define columns with types
   - Define relationships (FK constraints)
   - Write RLS policies

3. **Design the API layer**
   - Which operations need API routes vs Edge Functions?
   - What are the request/response shapes?
   - What validation is needed?

4. **Design the component tree**
   - What pages are needed?
   - What components are shared?
   - What's client vs server?

5. **Output a plan**
   - Numbered implementation steps
   - Start with schema/migration
   - End with UI

## Output Format

```
## Feature: [name]

### Data Model
[table definitions]

### API
[route definitions]

### Component Tree
[component hierarchy]

### RLS Policies
[policy definitions]

### Implementation Order
1. Migration: create tables
2. RLS: add policies
3. Types: regenerate database.ts
4. API: build routes/functions
5. Hooks: data fetching layer
6. UI: components and pages

### Risks
[potential problems to watch for]
```

## Domain context (examples)

For optional domain patterns: see `.claude/instincts.md` → "Example domain patterns"
For fintech features: amounts in smallest unit, immutable transaction records
For B2B features: multi-tenant RLS with `organization_id`
