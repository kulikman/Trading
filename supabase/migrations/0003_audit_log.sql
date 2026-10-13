-- 0003_audit_log.sql
-- Immutable audit trail for sensitive actions (auth, billing, profile changes).
-- Rows are insert-only — no user can update or delete their own audit entries.

create table if not exists public.audit_logs (
  id          bigint generated always as identity primary key,
  user_id     uuid references auth.users(id) on delete set null,
  action      text not null,                -- e.g. "auth.login", "billing.subscription_created"
  resource    text,                         -- e.g. "subscription:sub_xxx", "profile:uuid"
  metadata    jsonb not null default '{}',  -- IP, user-agent, diff, etc.
  created_at  timestamptz not null default now()
);

create index if not exists audit_logs_user_id_idx    on public.audit_logs(user_id);
create index if not exists audit_logs_created_at_idx on public.audit_logs(created_at desc);
create index if not exists audit_logs_action_idx     on public.audit_logs(action);

-- ── Row-Level Security ────────────────────────────────────────────────────────
alter table public.audit_logs enable row level security;

-- Users can read their own audit logs (e.g. "recent activity" page).
create policy "Users can read own audit logs"
  on public.audit_logs for select
  to authenticated
  using (auth.uid() = user_id);

-- No user-facing INSERT/UPDATE/DELETE policies — only service role writes logs.
