-- 0002_billing.sql
-- Stripe billing data: subscriptions linked to profiles.
-- Never store full card details here — Stripe handles that.

-- ── Add Stripe customer ID to profiles ───────────────────────────────────────
alter table public.profiles
  add column if not exists stripe_customer_id text unique;

-- ── Subscriptions ─────────────────────────────────────────────────────────────
create table if not exists public.subscriptions (
  id                   text primary key,          -- Stripe subscription ID (sub_xxx)
  user_id              uuid not null references auth.users(id) on delete cascade,
  status               text not null,             -- active | trialing | past_due | canceled | …
  price_id             text,                      -- Stripe price ID (price_xxx)
  product_id           text,                      -- Stripe product ID (prod_xxx)
  quantity             integer not null default 1,
  cancel_at_period_end boolean not null default false,
  current_period_start timestamptz,
  current_period_end   timestamptz,
  trial_start          timestamptz,
  trial_end            timestamptz,
  canceled_at          timestamptz,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

create trigger subscriptions_set_updated_at
  before update on public.subscriptions
  for each row execute function public.set_updated_at();

create index if not exists subscriptions_user_id_idx on public.subscriptions(user_id);

-- ── Row-Level Security ────────────────────────────────────────────────────────
alter table public.subscriptions enable row level security;

-- Users can only read their own subscriptions.
create policy "Users can read own subscriptions"
  on public.subscriptions for select
  to authenticated
  using (auth.uid() = user_id);

-- Only service role (webhook handler) writes subscriptions — no INSERT/UPDATE policies for users.
