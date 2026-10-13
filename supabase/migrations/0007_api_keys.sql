-- 0007_api_keys.sql
-- Developer API keys — only the SHA-256 hash is stored, never the plain key.
-- On creation the plain key is returned ONCE and then discarded.

create table if not exists public.api_keys (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  name         text not null check (char_length(name) between 1 and 64),
  key_hash     text not null unique,              -- SHA-256 of the raw key
  key_prefix   text not null,                    -- first 8 chars shown in UI ("sk_live_ab12...")
  last_used_at timestamptz,
  expires_at   timestamptz,                      -- null = never expires
  created_at   timestamptz not null default now()
);

create index if not exists api_keys_user_idx on public.api_keys(user_id);
create index if not exists api_keys_hash_idx on public.api_keys(key_hash);

-- ── Row-Level Security ────────────────────────────────────────────────────────
alter table public.api_keys enable row level security;

-- Users can read their own keys (never the hash).
create policy "Users can read own api keys"
  on public.api_keys for select
  to authenticated
  using (auth.uid() = user_id);

-- Users can create their own keys.
create policy "Users can create own api keys"
  on public.api_keys for insert
  to authenticated
  with check (auth.uid() = user_id);

-- Users can delete their own keys.
create policy "Users can delete own api keys"
  on public.api_keys for delete
  to authenticated
  using (auth.uid() = user_id);

-- Users can rename their own keys (update name only; key_hash must not change).
create policy "Users can update own api key name"
  on public.api_keys for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
