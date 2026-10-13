-- Club Checker database setup for Supabase.
-- Paste this whole file into the Supabase SQL Editor and click Run. Safe to run more than once.
--
-- Anyone with the page link (or the publishable key) can read reports, add reports
-- and upload screenshots. Nobody can edit or delete through the API; do that in the
-- Supabase dashboard (Table Editor / Storage).

create table if not exists public.reports (
  id          uuid primary key default gen_random_uuid(),
  team        text not null check (char_length(btrim(team)) between 1 and 60),
  team_key    text not null default '' check (char_length(team_key) <= 60),
  aka         text[] not null default '{}' check (cardinality(aka) <= 10 and char_length(array_to_string(aka, '')) <= 400),
  cheats      text[] not null default '{}' check (cardinality(cheats) <= 10 and char_length(array_to_string(cheats, '')) <= 400),
  players     text[] not null default '{}' check (cardinality(players) <= 20 and char_length(array_to_string(players, '')) <= 600),
  platform    text not null default '' check (char_length(platform) <= 20),
  score       text not null default '' check (char_length(score) <= 12),
  match_date  date not null default current_date,
  notes       text not null default '' check (char_length(notes) <= 2000),
  screenshots text[] not null default '{}' check (cardinality(screenshots) <= 6 and char_length(array_to_string(screenshots, '')) <= 600),
  reporter    text not null default '' check (char_length(reporter) <= 40),
  source      text not null default 'page' check (source in ('page', 'claude')),
  created_at  timestamptz not null default now()
);

alter table public.reports enable row level security;

drop policy if exists "Anyone can read reports" on public.reports;
create policy "Anyone can read reports" on public.reports
  for select to anon, authenticated using (true);

drop policy if exists "Anyone can add reports" on public.reports;
create policy "Anyone can add reports" on public.reports
  for insert to anon, authenticated with check (true);

grant select, insert on public.reports to anon, authenticated;
revoke update, delete, truncate on public.reports from anon, authenticated;

-- Screenshots: public to view, anyone can upload, 10 MB images only.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('screenshots', 'screenshots', true, 10485760, array['image/png', 'image/jpeg', 'image/webp', 'image/gif'])
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Anyone can upload screenshots" on storage.objects;
create policy "Anyone can upload screenshots" on storage.objects
  for insert to anon, authenticated with check (bucket_id = 'screenshots');
