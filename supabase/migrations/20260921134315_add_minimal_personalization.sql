-- Minimal onboarding preferences used by recipe generation.
-- Authentication remains owned by Supabase Auth and the existing profile RLS
-- policy continues to restrict every row to its owner.

alter table public.profiles
  drop constraint if exists profiles_activity_level_check,
  drop column if exists activity_level,
  add column preferred_tastes text[] not null default '{}',
  add column onboarding_completed_at timestamptz;

comment on column public.profiles.preferred_tastes is
  'Free-form, normalized taste and flavor preferences supplied during onboarding.';

comment on column public.profiles.onboarding_completed_at is
  'Server-controlled timestamp of the first completed onboarding submission.';
