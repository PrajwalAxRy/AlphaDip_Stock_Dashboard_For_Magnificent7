# AlphaDip Admin Guide

## Purpose

This guide is the operations handoff for AlphaDip production support, including score-weight updates, rollback, and incident basics.

## Prerequisites

- Streamlit Community Cloud app connected to this repository.
- Streamlit app secrets configured:
  - `FMP_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
- GitHub repository secrets configured for workflows with the same keys.

## Conviction Weight Updates

The scoring model weights are defined as module-level constants in `engine.py`:

- `PRICE_WEIGHT`
- `TREND_WEIGHT`
- `PEG_WEIGHT`
- `FCF_WEIGHT`
- `RS_WEIGHT`

### Rules

- Weights must sum to `100`.
- Keep each weight non-negative.
- Preserve missing-data neutral fallback behavior for PEG/FCF.

### Change Procedure

1. Create a branch (example: `feat/tune-score-weights-q2`).
2. Update weight constants in `engine.py`.
3. Run local checks:
   - `pytest -q`
4. Open PR with:
   - reason for new weighting
   - before/after examples for at least one ticker
5. Merge after CI is green.
6. In Streamlit Cloud, trigger a manual app reboot after deploy (if needed).

## Deployment Baseline (Streamlit Community Cloud)

1. In Streamlit Community Cloud, create app from repo:
   - Repository: `PrajwalAxRy/AlphaDip_Stock_Dashboard_For_Magnificent7`
   - Branch: `main`
   - Main file: `app.py`
2. In App Settings → Secrets, set:
   - `FMP_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
3. Deploy and verify the app loads.

## Production Smoke Test

After each production deploy, verify:

1. Command Center loads without errors.
2. Deep Dive opens from at least one ticker row.
3. Manual refresh completes and updates quote data.
4. Read-only mode banner behavior is correct during API limit simulations.

## Daily Workflow Validation

The scheduled pipeline is defined in `.github/workflows/daily_update.yml`.

Validate by running a manual dispatch:

1. GitHub → Actions → **Daily Snapshot Update** → **Run workflow**.
2. Test once with `dry_run=true`.
3. Test once with `dry_run=false` and a market date.
4. Confirm one snapshot per ticker/day (idempotent on rerun).

## Rollback Basics

Use rollback for severe regressions in UI, scoring output, or pipeline persistence.

1. Identify last known-good commit/tag.
2. Revert problematic commit(s) on a hotfix branch.
3. Run full suite: `pytest -q`.
4. Merge hotfix to `main`.
5. Redeploy Streamlit app (or reboot app to pull latest).
6. If needed, rerun daily workflow manually for the affected date.

## Incident Basics

### Common Incident Types

- `429` from FMP (rate-limited read-only mode)
- Supabase connectivity/auth failures
- stale quotes older than 24h
- market-closed edge behavior drift

### First Response Checklist

1. Capture timestamp, impacted tickers, and user-visible symptom.
2. Capture correlation ID from logs (if available).
3. Determine scope:
   - UI only
   - pipeline only
   - both
4. Apply mitigation:
   - rely on cached/Supabase fallback (read-only)
   - rerun workflow with `dry_run=true` first
   - rollback if customer-facing behavior is incorrect
5. Record incident summary and follow-up action item.

## Release Cadence Notes

- Keep `main` deployable.
- Prefer small milestone-scoped PRs.
- Use Conventional Commits.
