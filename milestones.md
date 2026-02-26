# AlphaDip 2026 — Engineering Milestones (Strict Checklist)

---

## How to Use This Document

- Work in **small vertical slices**.
- Keep `main` protected; use feature branches.
- Commit **frequently** (after each subtask, and midway through larger subtasks).
- Do not mark a milestone complete until:
  1. All milestone subtasks are checked.
  2. Milestone tests pass.
  3. **Regression tests from all previous milestones** pass.
  4. Changes are pushed and PR notes are written.

---

## Repository & Git Standards (Apply Throughout)

### Branching
- `main` is always deployable.
- Branch naming:
  - `feat/m1-scaffold`
  - `feat/m4-scoring-engine`
  - `fix/m8-weekend-fallback`

### Commit format (Conventional Commits)
- `feat(scope): short imperative summary`
- `fix(scope): short imperative summary`
- `test(scope): ...`
- `docs(scope): ...`
- `chore(scope): ...`
- `refactor(scope): ...`

### Commit frequency rules
- Subtask <= 60 minutes: commit at completion.
- Subtask > 60 minutes: commit at midpoint + completion.
- Any bug fix discovered while implementing: separate `fix(...)` commit.

### PR checklist (every milestone)
- [ ] No secrets committed.
- [ ] Local tests pass.
- [ ] CI checks pass.
- [ ] “How to test” section written in PR.
- [ ] Risks/limitations noted.

---

## Milestone 1 — Project Scaffold + Local Developer Environment

### Objective
Create a runnable baseline project with secure config handling and testing foundation.

### Strict Subtasks
- [x] Create base structure:
  - `.streamlit/secrets.toml.example`
  - `app.py`
  - `engine.py`
  - `database.py`
  - `cron_job.py`
  - `requirements.txt`
  - `tests/` (`unit`, `integration`, `e2e`, `fixtures`)
- [x] Add dependency list (`streamlit`, `pandas`, `yfinance`, `requests`, `supabase`, `pytest`, etc.).
- [x] Add `.gitignore` with Python/venv/secrets rules.
- [x] Add `README.md` quick-start section.
- [x] Add `pytest.ini` with basic markers (`unit`, `integration`, `e2e`).

### Required Artifacts
- [x] Repo structure from PRD exists.
- [x] `README.md` setup instructions are executable.
- [x] Test harness runs.

### Milestone Tests
- [x] `pytest -q` executes successfully (at least one smoke test).
- [x] App launches to a basic Streamlit shell without crashing.
- [x] Missing secrets produce a clear non-crashing error message.

### Regression Tests (Prior milestones)
- [x] N/A (first milestone).

### Commit Nudge (minimum)
- [x] `chore(repo): initialize alphadip project scaffold`
- [x] `chore(config): add gitignore and secrets template`
- [x] `test(setup): add pytest markers and smoke test`
- [x] `docs(readme): add local setup instructions`

---

## Milestone 2 — Database Schema + Data Access Layer (Supabase)

### Objective
Implement persistent watchlist and historical snapshot storage.

### Strict Subtasks
- [x] Create SQL migration for:
  - `watchlists`
  - `daily_snapshots`
  - `fundamentals_cache`
- [x] Add constraints/indexes:
  - Unique ticker in `watchlists`
  - Unique (`ticker`, `date`) for snapshots (or deterministic upsert policy)
- [x] Implement `database.py` connection/config loader.
- [x] Implement repository methods:
  - watchlist add/remove/list
  - snapshot insert/query
  - fundamentals cache upsert/query
- [x] Add defensive exception mapping for DB failures.

### Required Artifacts
- [x] Migration SQL file(s).
- [x] `database.py` repository API.
- [x] Integration test file for DB operations.

### Milestone Tests
- [x] Migration applies on clean DB.
- [x] CRUD tests for all 3 tables pass.
- [x] Duplicate snapshot handling behaves deterministically.
- [x] Connection failure surfaces controlled error.

### Regression Tests (M1 + current)
- [x] All Milestone 1 tests still pass.

### Commit Nudge (minimum)
- [x] `feat(db): add initial schema migration for watchlists snapshots cache`
- [x] `feat(db): implement supabase repositories for core entities`
- [x] `test(db): add integration tests for migrations and crud`
- [x] `fix(db): enforce deterministic duplicate snapshot behavior`

---

## Milestone 3 — External Data Layer (FMP + yfinance) + Caching

### Objective
Build reliable data clients while preserving API credits.

### Strict Subtasks
- [x] Implement FMP client endpoints:
  - quote
  - ratios-ttm
  - cash-flow-statement (quarter)
- [x] Implement yfinance client for 2-year OHLC data.
- [x] Normalize provider payloads into internal typed structures.
- [x] Implement caching policy:
  - quote: short TTL
  - fundamentals: long TTL / quarterly reuse
- [x] Implement 429 circuit-breaker state (`read_only=True` fallback).
- [x] Add logging for API latency/errors.

### Required Artifacts
- [x] `services/fmp_client.py`
- [x] `services/yfinance_client.py`
- [x] `services/cache.py` (or equivalent)
- [x] Unit tests with mocks for all external calls.

### Milestone Tests
- [x] Unit tests mock all external providers; no live network.
- [x] Null PEG response handled without exception.
- [x] Cache hit/miss behavior verified.
- [x] HTTP 429 flips system to read-only mode.

### Regression Tests (M1–M3)
- [x] Milestone 1 + 2 suites pass unchanged.

### Commit Nudge (minimum)
- [x] `feat(data): add fmp client for quote ratios cashflow endpoints`
- [x] `feat(data): add yfinance adapter for historical ohlc`
- [x] `feat(cache): add fundamentals and quote caching policy`
- [x] `test(data): add mocked provider tests and 429 scenario`

---

## Milestone 4 — Scoring Engine (Monitor Meter + Conviction Score)

### Objective
Translate PRD formulas into deterministic pure functions.

### Strict Subtasks
- [x] Implement price-gap calculation (% below 52-week high).
- [x] Implement monitor meter bands and score mapping.
- [x] Implement weighted components:
  - Price Architecture (30)
  - Trend Confirmation (20)
  - PEG (20)
  - FCF safety (15)
  - Relative strength vs S&P (15)
- [x] Clamp final score to 0–100.
- [x] Implement `is_recovery` (`price > 50d MA`).
- [x] Implement neutral fallback for missing fundamental values.

### Required Artifacts
- [x] `engine.py` complete with small, testable functions.
- [x] Reference fixture case for manual parity check.

### Milestone Tests
- [x] Boundary tests for meter and PEG thresholds.
- [x] Deterministic test for rounding and score clamp.
- [x] Missing-data fallback returns neutral component score.
- [x] Manual parity test: one stock (e.g., MSFT) matches expected output.

### Regression Tests (M1–M4)
- [x] Full prior test suites pass.

### Commit Nudge (minimum)
- [ ] `feat(engine): add price gap and monitor meter logic`
- [ ] `feat(engine): add weighted conviction scoring model`
- [ ] `test(engine): add boundary and reference parity tests`
- [ ] `fix(engine): stabilize rounding and fallback behavior`

---

## Milestone 5 — Daily Snapshot Pipeline + Scheduled Automation

### Objective
Automate market-close data pulls and historical snapshot persistence.

### Strict Subtasks
- [ ] Implement `cron_job.py` orchestration:
  - load tracked tickers
  - fetch data
  - compute score
  - persist snapshot
- [ ] Add idempotent run behavior for same day reruns.
- [ ] Add structured logging and error counts.
- [ ] Add GitHub Action workflow scheduled at 4:05 PM EST.
- [ ] Add manual trigger (`workflow_dispatch`) and dry-run mode.

### Required Artifacts
- [ ] `.github/workflows/daily_update.yml`
- [ ] End-to-end pipeline test file.

### Milestone Tests
- [ ] Pipeline inserts expected snapshots with mocked providers.
- [ ] Rerun same date does not duplicate rows.
- [ ] Workflow YAML validates and executes in CI.
- [ ] Dry-run does not write to DB.

### Regression Tests (M1–M5)
- [ ] Full prior suites pass.

### Commit Nudge (minimum)
- [ ] `feat(cron): add daily snapshot generation pipeline`
- [ ] `ci(cron): schedule daily market-close workflow`
- [ ] `test(cron): add idempotency and dry-run coverage`
- [ ] `chore(logging): add structured pipeline logs`

---

## Milestone 6 — Command Center (Main Dashboard)

### Objective
Deliver watchlist management and global ticker dashboard.

### Strict Subtasks
- [ ] Build ticker add/remove UI with DB persistence.
- [ ] Render dashboard rows with:
  - ticker + price
  - price gap
  - monitor meter (color coding)
  - trend icon (🚀 / 📉)
  - deep-dive action
- [ ] Implement manual refresh button with “lite” behavior (quote-first).
- [ ] Add mobile-responsive layout and `use_container_width=True` charts/tables.
- [ ] Add explicit read-only mode banner when circuit breaker is active.

### Required Artifacts
- [ ] `app.py` command center view.
- [ ] UI helper module(s).

### Milestone Tests
- [ ] Add/remove ticker flow works and persists.
- [ ] Dashboard renders required columns/indicators.
- [ ] Manual refresh updates quote without unnecessary fundamentals calls.
- [ ] Local latency check under target conditions (<3 seconds initial load).

### Regression Tests (M1–M6)
- [ ] Full prior suites pass.

### Commit Nudge (minimum)
- [ ] `feat(ui): add watchlist management controls`
- [ ] `feat(ui): add command center table with meter and trend`
- [ ] `feat(ui): add manual refresh and read-only banner`
- [ ] `test(ui): add dashboard interaction tests`

---

## Milestone 7 — Deep Dive View + Analyst Commentary

### Objective
Deliver per-ticker analytical page with historical context.

### Strict Subtasks
- [ ] Add deep-dive navigation flow from dashboard.
- [ ] Display 90-day conviction score chart from `daily_snapshots`.
- [ ] Show component-level score breakdown and raw metrics.
- [ ] Implement dynamic commentary templates (if/else rules).
- [ ] Show “Data Unavailable” badge for missing fundamentals.

### Required Artifacts
- [ ] Deep-dive UI module.
- [ ] Data transformation helper for chart series.

### Milestone Tests
- [ ] 90-day series displays sorted, accurate values.
- [ ] Component totals align with engine output.
- [ ] Missing PEG/FCF shows badge and no crash.
- [ ] Commentary text path changes under different score profiles.

### Regression Tests (M1–M7)
- [ ] Full prior suites pass.

### Commit Nudge (minimum)
- [ ] `feat(ui): add deep dive page and routing`
- [ ] `feat(ui): add conviction history chart and score breakdown`
- [ ] `feat(ui): add commentary rules and data-unavailable badge`
- [ ] `test(ui): add deep dive rendering and integrity tests`

---

## Milestone 8 — Edge Cases, Reliability, and Graceful Degradation

### Objective
Satisfy PRD error-handling requirements under real-world failures.

### Strict Subtasks
- [ ] Implement weekend/market-closed behavior using latest valid snapshot.
- [ ] Implement stale quote guard (>24h) with status indicator.
- [ ] Harden missing/null payload handling for all providers.
- [ ] Ensure 429 read-only mode uses cached Supabase data only.
- [ ] Centralize user-safe error messaging and logging correlation IDs.

### Required Artifacts
- [ ] Market status utility module.
- [ ] Error-handling utility module.

### Milestone Tests
- [ ] Sunday simulation uses Friday snapshot and avoids live quote fetch.
- [ ] 429 simulation keeps app usable in read-only mode.
- [ ] Missing fundamentals never crash engine/UI/pipeline.
- [ ] Stale-data status appears correctly.

### Regression Tests (M1–M8)
- [ ] Full prior suites pass.

### Commit Nudge (minimum)
- [ ] `feat(resilience): add market closed fallback behavior`
- [ ] `feat(resilience): add stale quote and read-only handling`
- [ ] `fix(resilience): normalize null provider payload paths`
- [ ] `test(resilience): add weekend 429 and stale data scenarios`

---

## Milestone 9 — Test Hardening + CI Quality Gates

### Objective
Build robust, deterministic, maintainable test and quality pipelines.

### Strict Subtasks
- [ ] Expand test markers and enforce marker discipline.
- [ ] Add deterministic fixtures/factories for OHLC and fundamentals.
- [ ] Add coverage reporting and gate (recommended: core modules >= 85%).
- [ ] Add CI matrix (Windows + Linux, supported Python versions).
- [ ] Add “no live network in unit tests” guard.
- [ ] Add artifact uploads for failures and coverage outputs.

### Required Artifacts
- [ ] Updated `pytest.ini`.
- [ ] Updated CI workflow.
- [ ] Shared fixtures in `tests/conftest.py`.

### Milestone Tests
- [ ] Unit, integration, e2e suites can run independently.
- [ ] Coverage gate enforces threshold.
- [ ] Flaky test detection pass (no non-deterministic failures in repeated runs).
- [ ] CI matrix is green.

### Regression Tests (M1–M9)
- [ ] Full historical suite passes under CI matrix.

### Commit Nudge (minimum)
- [ ] `test(quality): add deterministic fixture factories`
- [ ] `ci(quality): enforce coverage gate and matrix builds`
- [ ] `test(quality): block live network in unit test scope`
- [ ] `chore(ci): publish test artifacts on failure`

---

## Milestone 10 — Deployment, Verification, and Handoff

### Objective
Release to Streamlit Community Cloud and complete operational handoff.

### Strict Subtasks
- [ ] Deploy app to Streamlit Community Cloud.
- [ ] Configure required secrets:
  - `FMP_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
- [ ] Validate scheduled workflow in production repo.
- [ ] Execute UAT scenarios from PRD:
  - logic verification
  - mobile stress test
  - persistence over 24 hours
- [ ] Produce handoff docs:
  - admin guide (weight updates)
  - operations notes (rollback, incident basics)

### Required Artifacts
- [ ] Public app URL.
- [ ] `docs/admin_guide.md`.
- [ ] `docs/uat_checklist.md`.
- [ ] Final release tag.

### Milestone Tests
- [ ] Production smoke test passes (dashboard, deep-dive, refresh).
- [ ] Mobile checks pass on iPhone and Android (no horizontal overflow).
- [ ] New snapshot appears after next scheduled run.
- [ ] Release candidate regression suite passes unchanged.

### Regression Tests (M1–M10)
- [ ] Final full suite green before release tag.

### Commit Nudge (minimum)
- [ ] `chore(deploy): configure streamlit cloud deployment`
- [ ] `docs(ops): add admin guide and uat checklist`
- [ ] `chore(release): prepare v1.0.0 release notes`
- [ ] `release: v1.0.0`

---

## Python Testing Best Practices (Mandatory)

- Use `pytest` with clear markers: `unit`, `integration`, `e2e`, `slow`.
- Keep **unit tests isolated**:
  - mock FMP and yfinance calls
  - no real network
  - deterministic timestamps and data
- Keep **integration tests isolated**:
  - separate test DB/schema
  - clean setup/teardown
- Use fixtures/factories for consistent OHLC, PEG, FCF, and expected score cases.
- Freeze time when validating weekend/market-close behavior.
- Prefer small pure functions in `engine.py` and test them directly.
- Assert both value correctness and failure behavior (fallback/edge cases).
- Run tests in CI on every PR; do not merge red builds.

---

## Anti-Patterns to Avoid

- Calling fundamentals API on every app refresh.
- Mixing UI rendering with business logic and DB calls in one function.
- Writing tests against live APIs.
- Skipping timezone handling for market-close logic.
- Non-idempotent cron writes that duplicate daily snapshots.
- Large “mega commits” that hide regressions.
- Hardcoding secrets or printing credentials in logs.

---

## Definition of Done (Global)

Project is done only when:
- [ ] All 10 milestones are completed.
- [ ] All milestone and cumulative regression tests pass.
- [ ] App is live on Streamlit Community Cloud.
- [ ] Daily automation runs and populates historical snapshots.
- [ ] Handoff docs are complete and understandable by another engineer.
