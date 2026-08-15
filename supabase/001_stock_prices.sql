-- Run this once in the Supabase SQL Editor (same project as pp-sahamdarinol).
-- Separate table from `holdings` etc -- doesn't touch the member-gated data.

create table if not exists stock_prices (
  ticker text primary key,
  price numeric not null,
  updated_at timestamptz not null default now()
);

alter table stock_prices enable row level security;

-- Public read (needed so the static site can fetch prices with the anon key).
drop policy if exists "stock_prices_public_read" on stock_prices;
create policy "stock_prices_public_read"
  on stock_prices for select
  to anon
  using (true);

-- No insert/update/delete policy for anon -- only the service_role key
-- (used by api/update-prices.js) can write, service_role bypasses RLS.
