-- Forward Desk persistence layer (Supabase / Postgres).
--   runs             one row per saved setup: the same "forward-desk-session" JSON the dashboard exports.
--                    Private: row-level security limits every operation to the signed-in owner.
--   price_snapshots  live-price history written by python/refresh_live.py --push (service role only).
--                    Readable by anyone (public market data), never writable from the browser.

create table public.runs (
  id         uuid primary key default gen_random_uuid(),
  owner      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  name       text not null check (char_length(name) between 1 and 80),
  instrument text not null check (char_length(instrument) between 1 and 80),
  session    jsonb not null check (jsonb_typeof(session) = 'object' and pg_column_size(session) < 1000000),
  summary    jsonb not null default '{}'::jsonb check (jsonb_typeof(summary) = 'object')
);
create index runs_owner_created_idx on public.runs (owner, created_at desc);

alter table public.runs enable row level security;
-- (select auth.uid()) is evaluated once per statement instead of once per row.
create policy runs_select on public.runs for select to authenticated using (owner = (select auth.uid()));
create policy runs_insert on public.runs for insert to authenticated with check (owner = (select auth.uid()));
create policy runs_update on public.runs for update to authenticated using (owner = (select auth.uid())) with check (owner = (select auth.uid()));
create policy runs_delete on public.runs for delete to authenticated using (owner = (select auth.uid()));
revoke all on public.runs from anon;

create table public.price_snapshots (
  id         bigint generated always as identity primary key,
  instrument text not null,
  ts         timestamptz not null,
  spot       numeric not null check (spot > 0),
  source     text not null,
  fetched_at timestamptz not null default now(),
  unique (instrument, ts, source)
);
create index price_snapshots_instrument_ts_idx on public.price_snapshots (instrument, ts desc);

alter table public.price_snapshots enable row level security;
create policy price_snapshots_read on public.price_snapshots for select to anon, authenticated using (true);
revoke insert, update, delete on public.price_snapshots from anon, authenticated;   -- only the service role (bypasses RLS) writes
