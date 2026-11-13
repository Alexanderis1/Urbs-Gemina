-- Role tiers and the sports manager update log. No personal data beyond the auth user id:
-- account_ref is an organisational account ("org:<slug>"), never a person's name.

create table if not exists public.user_roles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  tier text not null default 'citizen' check (tier in ('citizen', 'office')),
  granted_at timestamptz not null default now()
);

alter table public.user_roles enable row level security;

-- A user can read their own tier (to show the right screens). Only the service role or an admin
-- in the dashboard can grant "office"; there is no insert/update policy for browser users.
create policy "read own tier" on public.user_roles
  for select using (auth.uid() = user_id);

create table if not exists public.sports_manager_updates (
  id bigint generated always as identity primary key,
  facility_id text not null,
  field text not null check (field in ('disciplines', 'hours', 'accessibility', 'contact', 'name')),
  value jsonb,
  account_ref text not null check (account_ref ~ '^org:[a-z0-9-]+$'),
  confirmed_at timestamptz not null,
  user_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);

alter table public.sports_manager_updates enable row level security;

-- Office users can read the log (audit). Writes go only through the "tools" edge function (service role).
create policy "office reads manager updates" on public.sports_manager_updates
  for select using (exists (select 1 from public.user_roles r where r.user_id = auth.uid() and r.tier = 'office'));
