-- 0004_organizations.sql
-- Multi-tenant organizations: orgs, members, invites.
-- Pattern: every table has RLS enabled in the same migration.

-- ── Organizations ─────────────────────────────────────────────────────────────
create table if not exists public.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (char_length(name) between 1 and 100),
  slug        text unique not null check (slug ~ '^[a-z0-9-]+$' and char_length(slug) between 2 and 48),
  logo_url    text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger organizations_set_updated_at
  before update on public.organizations
  for each row execute function public.set_updated_at();

alter table public.organizations enable row level security;

-- ── Org Members ───────────────────────────────────────────────────────────────
create type public.org_role as enum ('owner', 'admin', 'member');

create table if not exists public.org_members (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        public.org_role not null default 'member',
  created_at  timestamptz not null default now(),
  unique (org_id, user_id)
);

create index if not exists org_members_org_id_idx  on public.org_members(org_id);
create index if not exists org_members_user_id_idx on public.org_members(user_id);

alter table public.org_members enable row level security;

-- Members can read their org.
create policy "Org members can read organization"
  on public.organizations for select
  to authenticated
  using (
    exists (
      select 1 from public.org_members
      where org_members.org_id = organizations.id
        and org_members.user_id = auth.uid()
    )
  );

-- Any authenticated user can create an org (becomes owner automatically).
create policy "Authenticated users can create organizations"
  on public.organizations for insert
  to authenticated
  with check (true);

-- Only owners can update org details.
create policy "Org owners can update organization"
  on public.organizations for update
  to authenticated
  using (
    exists (
      select 1 from public.org_members
      where org_members.org_id = organizations.id
        and org_members.user_id = auth.uid()
        and org_members.role = 'owner'
    )
  );

-- Only owners can delete org.
create policy "Org owners can delete organization"
  on public.organizations for delete
  to authenticated
  using (
    exists (
      select 1 from public.org_members
      where org_members.org_id = organizations.id
        and org_members.user_id = auth.uid()
        and org_members.role = 'owner'
    )
  );

-- Members can see all members of their orgs.
create policy "Org members can view memberships"
  on public.org_members for select
  to authenticated
  using (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_members.org_id
        and m.user_id = auth.uid()
    )
  );

-- Only owners/admins can add members.
create policy "Org admins can add members"
  on public.org_members for insert
  to authenticated
  with check (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_members.org_id
        and m.user_id = auth.uid()
        and m.role in ('owner', 'admin')
    )
  );

-- Only owners can change roles; admins can't promote to owner.
create policy "Org owners can update roles"
  on public.org_members for update
  to authenticated
  using (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_members.org_id
        and m.user_id = auth.uid()
        and m.role = 'owner'
    )
  );

-- Owners/admins can remove members; members can remove themselves.
create policy "Members can be removed by owners, admins, or themselves"
  on public.org_members for delete
  to authenticated
  using (
    user_id = auth.uid()
    or exists (
      select 1 from public.org_members as m
      where m.org_id = org_members.org_id
        and m.user_id = auth.uid()
        and m.role in ('owner', 'admin')
    )
  );

-- ── Auto-assign creator as owner ─────────────────────────────────────────────
create or replace function public.handle_new_organization()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.org_members (org_id, user_id, role)
  values (new.id, auth.uid(), 'owner');
  return new;
end;
$$;

create trigger on_organization_created
  after insert on public.organizations
  for each row execute function public.handle_new_organization();

-- ── Org Invites ───────────────────────────────────────────────────────────────
create table if not exists public.org_invites (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references public.organizations(id) on delete cascade,
  invited_by  uuid not null references auth.users(id) on delete cascade,
  email       text not null check (email ~* '^[^@]+@[^@]+\.[^@]+$'),
  role        public.org_role not null default 'member',
  token       text unique not null default encode(gen_random_bytes(32), 'hex'),
  expires_at  timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  created_at  timestamptz not null default now(),
  unique (org_id, email)
);

create index if not exists org_invites_org_id_idx on public.org_invites(org_id);
create index if not exists org_invites_token_idx  on public.org_invites(token);

alter table public.org_invites enable row level security;

-- Org admins can view invites for their org.
create policy "Org admins can view invites"
  on public.org_invites for select
  to authenticated
  using (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_invites.org_id
        and m.user_id = auth.uid()
        and m.role in ('owner', 'admin')
    )
  );

-- Org admins can create invites.
create policy "Org admins can create invites"
  on public.org_invites for insert
  to authenticated
  with check (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_invites.org_id
        and m.user_id = auth.uid()
        and m.role in ('owner', 'admin')
    )
  );

-- Org admins can delete (revoke) invites.
create policy "Org admins can revoke invites"
  on public.org_invites for delete
  to authenticated
  using (
    exists (
      select 1 from public.org_members as m
      where m.org_id = org_invites.org_id
        and m.user_id = auth.uid()
        and m.role in ('owner', 'admin')
    )
  );
