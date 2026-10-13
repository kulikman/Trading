-- 0001_init_profiles.sql
-- Canonical example: a user-owned table with RLS enabled in the same migration.
-- CLAUDE.md rule: "RLS enabled on every table, policies in the migration that creates it."
--
-- `profiles` extends Supabase Auth's `auth.users` 1:1 with public profile data.
-- Treat this file as a copy-paste template for new tables — every new table
-- must follow the same pattern: enable RLS + define policies in one place.

-- ── Schema ───────────────────────────────────────────────────────────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  username    text unique not null check (char_length(username) between 2 and 32),
  full_name   text,
  avatar_url  text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Auto-update `updated_at` on every row change.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- ── Row-Level Security ───────────────────────────────────────────────────────
alter table public.profiles enable row level security;

-- Anyone authenticated can read any profile (public-by-default; tighten if needed).
create policy "Profiles are readable by authenticated users"
  on public.profiles for select
  to authenticated
  using (true);

-- A user may only insert their own row (id must match the JWT subject).
create policy "Users can create their own profile"
  on public.profiles for insert
  to authenticated
  with check (auth.uid() = id);

-- A user may only update their own row.
create policy "Users can update their own profile"
  on public.profiles for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- A user may only delete their own row.
create policy "Users can delete their own profile"
  on public.profiles for delete
  to authenticated
  using (auth.uid() = id);

-- ── Auto-create profile on signup ────────────────────────────────────────────
-- Whenever a new auth user is created, mirror them into `profiles`.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, username)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'username', split_part(new.email, '@', 1))
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
