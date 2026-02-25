# Copilot Instructions for AlphaDip 2026

## Quick Start (Required)
- Before making any code changes, activate the project virtual environment:
	- PowerShell: `./AlphDipVenv/Scripts/Activate.ps1`
- This is mandatory for all implementation, testing, and tooling commands.

## Current repo state (important)
- This repository is currently **planning-first**: implementation code is not present yet.
- Treat [PRD.md](../PRD.md) as product and architecture source of truth.
- Treat [milestones.md](../milestones.md) as the execution and quality gate contract.

## Product architecture to preserve
- System flow is **Trigger → Monitor → Confirm** (see PRD).
- Data sources: **FMP** for quote/PEG/FCF and **yfinance** for 2-year OHLC.
- Persistence: **Supabase/PostgreSQL** with `watchlists`, `daily_snapshots`, `fundamentals_cache`.
- UI: **Streamlit** with two views: Command Center + Deep Dive.
- Daily automation: scheduled pipeline at market close to compute/persist conviction snapshots.

## Target module boundaries (when creating code)
- `app.py`: Streamlit UI and view orchestration only.
- `engine.py`: pure scoring functions (price gap, monitor meter, conviction score).
- `database.py`: Supabase access layer (CRUD/upsert/query, deterministic duplicate handling).
- `cron_job.py`: orchestration for daily snapshot pipeline.
- `services/`: provider clients + caching (`fmp_client.py`, `yfinance_client.py`, `cache.py`).
- `tests/`: `unit`, `integration`, `e2e`, `fixtures`.

## Required domain logic conventions
- Conviction score is 0–100 weighted model: Price 30, Trend 20, PEG 20, FCF 15, RS 15.
- `is_recovery` is defined as `price > 50d MA`.
- Missing PEG/FCF must use a neutral fallback and never crash UI/pipeline.
- 429 from FMP must trigger **read-only** mode backed by cached/Supabase data.
- Weekend/market-closed sessions should use latest valid snapshot (no stale live fetches).

## Developer workflow expectations
- Use small milestone-scoped vertical slices from [milestones.md](../milestones.md).
- **Very important:** before making any code changes, ensure the `AlphDipVenv` virtual environment is activated.
- Keep `main` deployable; use branches like `feat/m4-scoring-engine`.
- Use Conventional Commits (`feat(scope): ...`, `fix(scope): ...`, etc.).
- Commit at subtask boundaries (and midpoint for long subtasks).
- Before marking work done: run milestone tests + regression tests from prior milestones.

## Testing and CI rules to enforce
- `pytest` markers: `unit`, `integration`, `e2e` (plus `slow` where needed).
- Unit tests must mock all external APIs; no live network.
- Add deterministic fixtures for OHLC/fundamentals and time-dependent logic.
- Cron writes must be idempotent for same-day reruns.
- CI should include quality gates (coverage + matrix) as milestones progress.

## Security and configuration
- Never hardcode or log secrets.
- Use Streamlit secrets for `FMP_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`.
- Keep `.streamlit/secrets.toml` out of version control; maintain an example template.

## Anti-patterns to avoid in this project
- Fetching fundamentals on every UI refresh.
- Mixing UI rendering with engine/DB logic in one large function.
- Non-idempotent snapshot inserts.
- Ignoring timezone/market-close behavior in scheduling and fallback logic.
