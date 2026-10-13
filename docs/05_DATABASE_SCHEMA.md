# Database Schema

## Database
PostgreSQL via Supabase. All migrations in `supabase/migrations/`.

**Rules:**
- Every schema change requires a migration file (`pnpm supabase migration new <name>`)
- RLS must be enabled on every table (see migration files for policies)
- Regenerate types after schema changes: `pnpm supabase gen types typescript --project-id <id> > src/types/database.ts`
- Never manually edit production DB — always use migrations

---

## Core Tables (scaffolded in template)

### profiles

Extends Supabase `auth.users`. Created automatically on signup via trigger.

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | FK → auth.users.id |
| email | text | ✅ | User email (synced from auth) |
| full_name | text | | Display name |
| avatar_url | text | | Profile image URL |
| role | text | ✅ | user / admin / super_admin |
| stripe_customer_id | text | | Stripe customer ID |
| onboarding_completed | bool | ✅ | Whether onboarding is done |
| created_at | timestamptz | ✅ | |
| updated_at | timestamptz | ✅ | |

**RLS:** User reads own row. Admin reads all.

---

### subscriptions

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| user_id | uuid | ✅ | FK → profiles.id |
| stripe_subscription_id | text | ✅ | Stripe subscription ID |
| stripe_price_id | text | | Active price ID |
| stripe_product_id | text | | Active product ID |
| status | text | ✅ | active / canceled / past_due / … |
| current_period_end | timestamptz | | Renewal date |
| created_at | timestamptz | ✅ | |
| updated_at | timestamptz | ✅ | |

**RLS:** User reads own row. Admin reads all.

---

### orgs

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| name | text | ✅ | Organization display name |
| slug | text | ✅ | URL-safe unique identifier |
| owner_id | uuid | ✅ | FK → profiles.id |
| created_at | timestamptz | ✅ | |

**RLS:** Members can read. Owner can update/delete.

---

### org_members

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| org_id | uuid | ✅ | FK → orgs.id |
| user_id | uuid | ✅ | FK → profiles.id |
| role | text | ✅ | owner / admin / member |
| invited_by | uuid | | FK → profiles.id |
| accepted_at | timestamptz | | Null if invite pending |
| expires_at | timestamptz | | Invite expiry |
| created_at | timestamptz | ✅ | |

**RLS:** Member reads own rows. Org owner reads all org rows.

---

### notifications

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| user_id | uuid | ✅ | FK → profiles.id |
| title | text | ✅ | Notification heading |
| body | text | | Detail text |
| kind | text | ✅ | info / success / warning / error |
| href | text | | Optional link |
| read_at | timestamptz | | Null if unread |
| created_at | timestamptz | ✅ | |

**RLS:** User reads/updates own notifications only.

---

### api_keys

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| user_id | uuid | ✅ | FK → profiles.id |
| name | text | ✅ | Human-readable label |
| key_hash | text | ✅ | SHA-256 hash of the key |
| last_used_at | timestamptz | | Updated on each use |
| created_at | timestamptz | ✅ | |

**RLS:** User reads/deletes own keys. Plain key shown once at creation; only hash stored.

---

### audit_logs

| Field | Type | Required | Description |
|---|---|:---:|---|
| id | uuid | ✅ | PK |
| actor_id | uuid | | FK → profiles.id (null for system) |
| action | text | ✅ | e.g. `user.role.changed`, `org.deleted` |
| entity_type | text | ✅ | Table name: `profiles`, `orgs`, … |
| entity_id | uuid | | ID of affected row |
| metadata | jsonb | | Extra context (before/after values) |
| created_at | timestamptz | ✅ | |

**RLS:** Admin reads all. No user writes (insert via service role only).

---

## Your Feature Tables

Add your domain-specific tables here. Follow this pattern:

```sql
-- supabase/migrations/YYYYMMDDHHMMSS_create_[table].sql
CREATE TABLE public.[table_name] (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  -- your fields
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.[table_name] ENABLE ROW LEVEL SECURITY;

-- User can only access their own rows
CREATE POLICY "[table]_owner" ON public.[table_name]
  FOR ALL USING (auth.uid() = user_id);
```

---

## Migration Workflow

```bash
# Create migration
pnpm supabase migration new create_[table_name]

# Apply locally
pnpm supabase db reset

# Regenerate TypeScript types
pnpm supabase gen types typescript --project-id <id> > src/types/database.ts
```
