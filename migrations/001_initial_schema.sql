create extension if not exists pgcrypto;

create table if not exists watchlists (
    id uuid primary key default gen_random_uuid(),
    ticker text not null unique,
    added_at timestamptz not null default timezone('utc', now())
);

create table if not exists daily_snapshots (
    id bigserial primary key,
    ticker text not null references watchlists(ticker) on delete cascade,
    date date not null,
    price_gap double precision not null,
    conviction_score integer not null check (conviction_score between 0 and 100),
    is_recovery boolean not null,
    created_at timestamptz not null default timezone('utc', now()),
    unique (ticker, date)
);

create index if not exists idx_daily_snapshots_ticker_date on daily_snapshots (ticker, date desc);
create index if not exists idx_daily_snapshots_date on daily_snapshots (date);

create table if not exists fundamentals_cache (
    ticker text primary key references watchlists(ticker) on delete cascade,
    as_of_date date not null,
    peg_ratio double precision,
    fcf_yield double precision,
    raw_payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_fundamentals_cache_as_of_date on fundamentals_cache (as_of_date desc);
