-- AgentAQI public multi-user schema. Run once in Supabase SQL Editor.
create extension if not exists pgcrypto;

create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (char_length(display_name) <= 24),
  city text not null default 'taipei' check (char_length(city) <= 40),
  sensitivity text not null default 'general' check (sensitivity in ('general', 'sensitive')),
  activity text not null default 'commute' check (activity in ('commute', 'walk', 'run', 'cycle', 'outdoor')),
  threshold integer not null default 100 check (threshold between 50 and 180),
  updated_at timestamptz not null default now()
);

create table if not exists public.agent_integrations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  platform text not null,
  status text not null default 'connected' check (status in ('connected', 'provisioning', 'ready', 'error')),
  platform_user_id text,
  platform_user_name text,
  platform_space_id text,
  platform_space_name text,
  hermes_profile text,
  provision_detail text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, platform)
);

alter table public.user_profiles enable row level security;
alter table public.agent_integrations enable row level security;

-- Migration from the earlier LINE prototype: discard obsolete rows/table and
-- narrow the public integration surface to Discord only.
delete from public.agent_integrations where platform <> 'discord';
alter table public.agent_integrations drop constraint if exists agent_integrations_platform_check;
alter table public.agent_integrations add constraint agent_integrations_platform_check check (platform = 'discord');
drop table if exists public.agent_binding_codes;

drop policy if exists "profiles_select_own" on public.user_profiles;
create policy "profiles_select_own" on public.user_profiles for select using (auth.uid() = user_id);
drop policy if exists "profiles_insert_own" on public.user_profiles;
create policy "profiles_insert_own" on public.user_profiles for insert with check (auth.uid() = user_id);
drop policy if exists "profiles_update_own" on public.user_profiles;
create policy "profiles_update_own" on public.user_profiles for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "integrations_select_own" on public.agent_integrations;
create policy "integrations_select_own" on public.agent_integrations for select using (auth.uid() = user_id);

-- Integration writes are backend-only through the service-role key.

create index if not exists agent_integrations_user_id_idx on public.agent_integrations(user_id);
