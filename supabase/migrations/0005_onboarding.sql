-- 0005_onboarding.sql
-- Track per-user onboarding progress.
-- The wizard checks `onboarding_completed` and redirects to /onboarding when false.

alter table public.profiles
  add column if not exists onboarding_completed boolean not null default false,
  add column if not exists onboarding_step      integer not null default 0;

comment on column public.profiles.onboarding_completed is
  'True once the user has finished the onboarding wizard.';
comment on column public.profiles.onboarding_step is
  'Last completed step index (0-based). Used to resume mid-wizard.';
