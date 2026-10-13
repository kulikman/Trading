# Supabase

Database migrations, RLS policies, and seed data for this project.

## Layout

```
supabase/
├── migrations/        # SQL migrations — one numbered file per change
└── README.md          # this file
```

`supabase/migrations/0001_init_profiles.sql` is the canonical example: a
user-owned table with RLS enabled in the same migration. Copy its
structure for every new table you create.

## Workflow

### Local development

```bash
# 1. Install the Supabase CLI (one-time)
brew install supabase/tap/supabase

# 2. Start the local stack
supabase start

# 3. Apply migrations
supabase db reset    # wipes + re-applies all migrations from scratch
```

### Template QA

This repository is a starter template. Do not link it to, or push migrations
into, a shared remote Supabase project just to validate template changes.

Validate migrations against a local Supabase stack:

```bash
supabase start
supabase db reset
```

Only apply migrations to a remote project after a real project has been created
from the template and the target project ref is known.

### Creating a new migration

```bash
supabase migration new <descriptive_name>
# → creates supabase/migrations/<timestamp>_<name>.sql
```

Edit the file. Both schema **and** RLS policies must live in the same
migration — never ship a table without its policies.

### Applying to a remote project

```bash
supabase link --project-ref <your-project-id>
supabase db push
```

### Regenerating TypeScript types

After every schema change:

```bash
SUPABASE_PROJECT_ID=<your-project-id> pnpm supabase:types
```

This rewrites `src/types/database.ts` — commit the diff together with
the migration.

## Rules

1. **One table → one owning module.** Other modules call the owner's
   public functions, never raw SQL against foreign tables.
2. **RLS in the same migration** as the table. Never `alter table … enable
   row level security` in a separate file later.
3. **`security definer` functions** must `set search_path = public` to
   defeat search_path injection attacks.
4. **Never modify a shipped migration.** Fix-forward with a new file.
