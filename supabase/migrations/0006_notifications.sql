-- 0006_notifications.sql
-- In-app notification feed with Supabase Realtime support.

create table if not exists public.notifications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  title       text not null check (char_length(title) between 1 and 128),
  body        text,
  href        text,              -- optional deep-link inside the app
  read        boolean not null default false,
  kind        text not null default 'info'
                check (kind in ('info', 'success', 'warning', 'error')),
  created_at  timestamptz not null default now()
);

-- Index for fast per-user unread counts and feed queries.
create index if not exists notifications_user_unread_idx
  on public.notifications(user_id, read, created_at desc);

-- Enable row-level security.
alter table public.notifications enable row level security;

-- Users can only read their own notifications.
create policy "Users can read own notifications"
  on public.notifications for select
  to authenticated
  using (auth.uid() = user_id);

-- Users can mark their own notifications as read.
create policy "Users can update own notifications"
  on public.notifications for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Only service role inserts notifications (e.g. from webhooks / server actions).
-- No INSERT policy for authenticated role — prevents self-injection.

-- Enable Realtime for instant bell badge updates.
alter publication supabase_realtime add table public.notifications;
