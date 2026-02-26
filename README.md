# AlphaDip 2026

A conviction-based stock monitoring dashboard for the Magnificent 7 tech stocks. Built with Streamlit, powered by FMP and yfinance data, persisted in Supabase/PostgreSQL.

**System flow**: Trigger → Monitor → Confirm

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Module Reference](#module-reference)
  - [Core Modules](#core-modules)
  - [Service Layer](#service-layer)
- [Conviction Scoring Model](#conviction-scoring-model)
- [Database Schema](#database-schema)
- [Daily Automation Pipeline](#daily-automation-pipeline)
- [UI Views](#ui-views)
- [Resilience & Edge Cases](#resilience--edge-cases)
- [Testing](#testing)
- [Configuration & Secrets](#configuration--secrets)
- [Configurable Values & Tuning](#configurable-values--tuning)
- [GitHub Actions CI/CD](#github-actions-cicd)
- [Development Workflow](#development-workflow)
- [Milestones Completed](#milestones-completed)

---

## Quick Start

```powershell
# 1. Activate the virtual environment
./AlphDipVenv/Scripts/Activate.ps1       # PowerShell
# source ./AlphDipVenv/bin/activate      # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create local secrets file
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and fill in your keys

# 4. Run tests
pytest -q

# 5. Run the app
streamlit run app.py
```

If secrets are missing, the app shows a clear error message and does not crash.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit UI (app.py)                                  │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │ Command Center View │  │ Deep Dive View           │  │
│  │ (ui_helpers.py)     │  │ (deep_dive_ui.py)        │  │
│  └────────┬────────────┘  └────────┬─────────────────┘  │
│           │                        │                     │
│           ▼                        ▼                     │
│  ┌──────────────────────────────────────┐                │
│  │ engine.py — Pure Scoring Functions   │                │
│  └──────────────────┬───────────────────┘                │
│                     │                                    │
│  ┌──────────────────▼───────────────────┐                │
│  │ Data / Persistence Layer             │                │
│  │  ┌────────────┐ ┌─────────────────┐  │                │
│  │  │ database.py│ │ services/       │  │                │
│  │  │ (Supabase) │ │  fmp_client.py  │  │                │
│  │  │            │ │  yfinance_client│  │                │
│  │  │            │ │  cache.py       │  │                │
│  │  └────────────┘ └─────────────────┘  │                │
│  └──────────────────────────────────────┘                │
│                                                          │
│  ┌──────────────────────────────────────┐                │
│  │ Resilience Layer                     │                │
│  │  market_status.py | error_handling.py│                │
│  └──────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │ cron_job.py — Daily Pipeline (GitHub Actions / CLI)  │
  └──────────────────────────────────────────────────────┘
```

---

## Module Reference

### Core Modules

| File | Purpose | Key Exports |
|------|---------|-------------|
| `app.py` | Streamlit UI entry point & view orchestration | `main()`, `build_command_center_rows()`, `build_deep_dive_model()`, `CommandCenterResult` |
| `engine.py` | Pure conviction scoring functions (no I/O) | `build_conviction_result()`, `ConvictionResult`, `ConvictionBreakdown`, `calculate_price_gap_percent()`, `monitor_meter_from_price_gap()`, `is_recovery()` |
| `database.py` | Supabase access layer (CRUD/upsert/query) | `SupabaseRepository`, `DatabaseConfig`, `load_database_config()` |
| `cron_job.py` | Daily snapshot pipeline orchestration (CLI) | `run_daily_snapshot_pipeline()`, `PipelineSummary`, `run_from_cli()` |
| `deep_dive_ui.py` | Deep Dive page rendering & data models | `DeepDiveRenderModel`, `build_conviction_history_series()`, `build_dynamic_commentary()`, `render_deep_dive_page()` |
| `ui_helpers.py` | Shared UI utilities | `monitor_meter_label(band, score)` |

### Service Layer

| File | Purpose | Key Exports |
|------|---------|-------------|
| `services/fmp_client.py` | Financial Modeling Prep API client | `FMPClient`, `QuoteData`, `FundamentalsData`, `FMPClientError`, `FMPRateLimitError` |
| `services/yfinance_client.py` | yfinance wrapper for 2-year OHLC history | `YFinanceClient`, `OhlcBar`, `YFinanceClientError` |
| `services/cache.py` | In-memory TTL-based caching (quotes + fundamentals) | `AlphaDipCachePolicy`, `TTLCache` |
| `services/market_status.py` | Weekend/holiday detection, last-trading-date logic | `is_weekend()`, `is_market_closed()`, `is_market_open_now()`, `last_trading_date()`, `should_skip_live_fetch()` |
| `services/error_handling.py` | Correlation IDs, user-safe messages, stale detection | `generate_correlation_id()`, `user_safe_message()`, `log_error()`, `log_warning()`, `is_quote_stale()` |

---

## Conviction Scoring Model

The conviction score is a **0–100 weighted model** computed by `engine.py`:

| Component | Weight | Logic |
|-----------|--------|-------|
| **Price Architecture** | 30 | Normalized over 0–30% price gap range. Larger gap = higher score |
| **Trend Confirmation** | 20 | Full points if `price > 50-day MA` (recovery); 0 if below |
| **PEG** | 20 | PEG < 1.0 → full points; PEG ≥ 2.0 → 0; linear interpolation between |
| **FCF Safety** | 15 | Requires 3 ascending positive FCF quarters for full points |
| **Relative Strength** | 15 | Stock 1-month return vs S&P 500 1-month return |

**Missing data policy**: If PEG or FCF data is unavailable, the component receives a **neutral fallback** (half of max weight). The system never crashes on missing fundamentals.

### Monitor Meter Bands

| Band | Price Gap | Score | UI Label |
|------|-----------|-------|----------|
| Neutral | 0–15% | 1–3 | 🟢 Neutral |
| Watching | 15–25% | 4–7 | 🟠 Watching |
| Strike Zone | 25%+ | 8–10 | 🔴 Strike Zone |

### Recovery Detection

A stock is in **recovery** when `current_price > 50-day moving average`.

---

## Database Schema

Three PostgreSQL tables managed in Supabase (see `migrations/001_initial_schema.sql`):

### `watchlists`
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | Auto-generated |
| `ticker` | TEXT | Unique constraint |
| `added_at` | TIMESTAMPTZ | Default: now() |

### `daily_snapshots`
| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL (PK) | Auto-increment |
| `ticker` | TEXT (FK → watchlists) | Cascade delete |
| `date` | DATE | Unique with ticker |
| `price_gap` | DOUBLE PRECISION | |
| `conviction_score` | INTEGER | CHECK: 0–100 |
| `is_recovery` | BOOLEAN | |
| `created_at` | TIMESTAMPTZ | |

Indexes: `(ticker, date DESC)`, `(date)`

### `fundamentals_cache`
| Column | Type | Notes |
|--------|------|-------|
| `ticker` | TEXT (PK, FK → watchlists) | |
| `as_of_date` | DATE | |
| `peg_ratio` | DOUBLE PRECISION | Nullable |
| `fcf_yield` | DOUBLE PRECISION | Nullable |
| `raw_payload` | JSONB | |
| `updated_at` | TIMESTAMPTZ | |

**Idempotency**: Snapshot upserts use the `(ticker, date)` unique constraint — re-running the pipeline for the same day updates rather than duplicates.

---

## Daily Automation Pipeline

The pipeline (`cron_job.py`) runs at market close and:

1. Checks if the market is closed (weekend/holiday) — skips if so
2. Loads all tracked tickers from the watchlist
3. For each ticker: fetches quote, OHLC, fundamentals → computes conviction → persists snapshot
4. Emits structured logs and returns a `PipelineSummary`

### CLI Usage

```bash
# Normal run (today's date)
python cron_job.py

# Dry run — compute but don't write to DB
python cron_job.py --dry-run

# Specific date
python cron_job.py --date 2026-02-23

# Combined
python cron_job.py --dry-run --date 2026-02-23
```

### GitHub Actions Schedule

The workflow (`.github/workflows/daily_update.yml`) runs **Mon–Fri at 21:05 UTC** (≈ 4:05 PM ET, right after market close). It also supports `workflow_dispatch` for manual triggers with optional `dry_run` and `run_date` inputs.

---

## UI Views

### Command Center (Main Dashboard)

- **Watchlist management**: Add/remove tickers with DB persistence
- **Dashboard table**: Ticker, Price, Price Gap %, Monitor Meter (color-coded), Trend (🚀/📉), Deep Dive action
- **Manual refresh**: "Lite" mode fetches quotes only, skipping fundamentals
- **Read-only banner**: Displayed when FMP rate limit is active
- **Market-closed banner**: Displayed on weekends/holidays, shows cached data
- **Stale-data warning**: Shown when any quote is older than 24 hours

### Deep Dive View

- **90-day conviction history chart** from `daily_snapshots`
- **Component-level score breakdown** (Price, Trend, PEG, FCF, RS)
- **Raw metrics table** (current price, gap, 50D MA, 52W high, PEG, FCF quarters, returns)
- **Dynamic commentary** based on score profiles:
  - Score ≥ 75 + recovery → "Strong setup"
  - Score ≥ 60 → "Constructive"
  - Score ≥ 40 → "Mixed"
  - Score < 40 → "Low-conviction"
- **"Data Unavailable" badge** when PEG/FCF are missing

---

## Resilience & Edge Cases

### Weekend / Market-Closed Behavior
When the market is closed, the app serves the **latest valid snapshot** from Supabase instead of making live API calls. The pipeline skips processing entirely.

### Stale Quote Guard
Quotes older than **24 hours** are flagged with a warning banner listing the affected tickers. Data is still displayed, but the user is informed.

### FMP Rate Limit (HTTP 429)
When FMP returns a 429, the client sets `read_only = True`. All subsequent calls fall back to **cached Supabase data**. The UI shows a read-only mode banner.

### Missing / Null Payload Handling
- **FMP client**: Validates price > 0, uses `isinstance` guards on all response elements, handles `{"Error Message": ...}` responses
- **yfinance client**: `_safe_float()` / `_safe_int()` helpers handle NaN, Inf, and None; bars with `close ≤ 0` are skipped
- **Engine**: Missing PEG/FCF receive neutral fallback scores (never crash)

### Correlation IDs
Every error is logged with a 12-character correlation ID (UUID hex prefix). User-facing messages can reference this ID for support.

---

## Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_smoke.py              # Basic smoke tests (project name, missing secrets)
│   ├── test_engine.py             # Scoring engine boundaries, PEG/FCF thresholds, MSFT parity
│   ├── test_data_clients.py       # FMP/yfinance mocked client tests, 429 rate-limit
│   ├── test_cache_policy.py       # TTL expiry, quarter-aware cache invalidation
│   ├── test_command_center_ui.py  # Dashboard rendering, watchlist, read-only mode
│   ├── test_deep_dive_ui.py       # Deep dive page, history series, commentary
│   └── test_resilience.py         # M8: weekend fallback, 429 mode, null payloads, stale data
├── integration/
│   └── test_database_integration.py  # Supabase repository CRUD with fake client
├── e2e/
│   └── test_daily_snapshot_pipeline_e2e.py  # Full pipeline flow with fakes
└── fixtures/
    └── msft_reference_case.json   # Golden reference for MSFT scoring parity
```

### Running Tests

```bash
# Run all tests
pytest -v

# Run only unit tests
pytest -m unit -v

# Run only integration tests
pytest -m integration -v

# Run only e2e tests
pytest -m e2e -v

# Run a specific test file
pytest tests/unit/test_engine.py -v

# Run a specific test class
pytest tests/unit/test_resilience.py::TestMarketStatus -v

# Quick summary (minimal output)
pytest -q
```

### Test Markers (defined in `pytest.ini`)

| Marker | Purpose |
|--------|---------|
| `unit` | Fast, isolated tests — all external APIs mocked, no network |
| `integration` | Tests that use real infrastructure (DB with fake client) |
| `e2e` | End-to-end user flow tests |

### Current Test Count: **66 tests passing**

---

## Configuration & Secrets

### Required Secrets

| Key | Source | Used By |
|-----|--------|---------|
| `FMP_API_KEY` | [Financial Modeling Prep](https://financialmodelingprep.com/) | `services/fmp_client.py`, `cron_job.py` |
| `SUPABASE_URL` | [Supabase](https://supabase.com/) project URL | `database.py` |
| `SUPABASE_KEY` | Supabase anon or service key | `database.py` |

### Local Development

Copy the example template and fill in your keys:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

```toml
FMP_API_KEY = "your_fmp_api_key"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your_supabase_service_or_anon_key"
```

> **Never** commit `.streamlit/secrets.toml` — it is in `.gitignore`.

### GitHub Actions

Set the same three keys as **repository secrets** in GitHub → Settings → Secrets and variables → Actions.

---

## Configurable Values & Tuning

These are the key values you may want to adjust, and where to find them:

### Scoring Weights (`engine.py`)

| Constant | Default | Line |
|----------|---------|------|
| `PRICE_WEIGHT` | 30.0 | Top of file |
| `TREND_WEIGHT` | 20.0 | Top of file |
| `PEG_WEIGHT` | 20.0 | Top of file |
| `FCF_WEIGHT` | 15.0 | Top of file |
| `RS_WEIGHT` | 15.0 | Top of file |

> Weights must sum to 100. Changing them alters how the conviction score balances price action vs fundamentals.

### Cache TTLs (`services/cache.py`)

| Parameter | Default | Effect |
|-----------|---------|--------|
| `quote_ttl_seconds` | 60 (1 minute) | How often live quotes are re-fetched. Lower = more API calls |
| `fundamentals_ttl_seconds` | 8,208,000 (≈ 95 days) | Fundamentals refresh roughly once per quarter |

### Market Status (`services/market_status.py`)

| Value | Default | Notes |
|-------|---------|-------|
| `_STATIC_HOLIDAYS` | 6 fixed US holidays | Approximated dates — floating holidays (Thanksgiving) need manual update yearly |
| `_ET_OFFSET` | UTC-5 | Fixed offset; does not account for DST. For DST-aware detection, replace with `pytz` or `zoneinfo` |
| `_MARKET_OPEN_TIME` | 9:30 AM ET | NYSE regular session open |
| `_MARKET_CLOSE_TIME` | 4:00 PM ET | NYSE regular session close |

### Stale Data Threshold (`services/error_handling.py`)

| Value | Default | Effect |
|-------|---------|--------|
| `_STALE_THRESHOLD_HOURS` | 24 | Quotes older than this trigger a stale-data warning in the UI |

### FMP Client (`services/fmp_client.py`)

| Value | Default | Notes |
|-------|---------|-------|
| `base_url` | `https://financialmodelingprep.com` | Change for self-hosted or proxy |
| `timeout_seconds` | 15 | HTTP request timeout |

### Trading Day Constants (`app.py`, `cron_job.py`)

| Value | Default | Notes |
|-------|---------|-------|
| `TRADING_DAYS_1M` | 21 | Used for 1-month return calculation |
| `TRADING_DAYS_1Y` | 252 | Used for 52-week high from OHLC bars |

---

## GitHub Actions CI/CD

### Daily Snapshot Workflow

**File**: `.github/workflows/daily_update.yml`

- **Schedule**: Mon–Fri at 21:05 UTC (≈ 4:05 PM ET)
- **Trigger**: Also supports manual `workflow_dispatch`
- **Inputs** (manual only):
  - `dry_run` (boolean) — compute without writing to DB
  - `run_date` (string, YYYY-MM-DD) — override the run date
- **Required secrets**: `FMP_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`

---

## Development Workflow

### Branching

- `main` is always deployable
- Feature branches: `feat/m4-scoring-engine`, `fix/m8-weekend-fallback`

### Commit Conventions

[Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat(scope): short imperative summary
fix(scope): short imperative summary
test(scope): ...
docs(scope): ...
chore(scope): ...
refactor(scope): ...
```

### PR Checklist

- [ ] No secrets committed
- [ ] Local tests pass (`pytest -v`)
- [ ] CI checks pass
- [ ] "How to test" section written in PR
- [ ] Risks/limitations noted

### Key Anti-Patterns to Avoid

- Fetching fundamentals on every UI refresh (use cache)
- Mixing UI rendering with engine/DB logic
- Non-idempotent snapshot inserts
- Tests against live APIs (mock everything in unit tests)
- Ignoring timezone/market-close behavior
- Hardcoding or logging secrets

---

## Milestones Completed

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Project Scaffold + Local Dev Environment | ✅ |
| 2 | Database Schema + Data Access Layer (Supabase) | ✅ |
| 3 | External Data Layer (FMP + yfinance) + Caching | ✅ |
| 4 | Scoring Engine (Monitor Meter + Conviction Score) | ✅ |
| 5 | Daily Snapshot Pipeline + Scheduled Automation | ✅ |
| 6 | Command Center (Main Dashboard) | ✅ |
| 7 | Deep Dive View + Analyst Commentary | ✅ |
| 8 | Edge Cases, Reliability, and Graceful Degradation | ✅ |
| 9 | Test Hardening + CI Quality Gates | ⬜ |
| 10 | Deployment, Verification, and Handoff | ⬜ |

See `milestones.md` for the full strict checklist and acceptance criteria.