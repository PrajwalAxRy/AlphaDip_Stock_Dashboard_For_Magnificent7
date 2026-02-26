# AlphaDip v1.0.0 Release Notes

Release date: 2026-02-26

## Summary

`v1.0.0` is the first production release of AlphaDip, delivering the full Trigger → Monitor → Confirm workflow with Streamlit UI, deterministic conviction scoring, scheduled snapshot persistence, resilience safeguards, and quality-gated CI.

## Included Capabilities

- Command Center dashboard with watchlist management and manual refresh.
- Deep Dive view with 90-day conviction history, score breakdown, and commentary.
- Scoring engine with 0–100 weighted model:
  - Price Architecture (30)
  - Trend Confirmation (20)
  - PEG (20)
  - FCF Safety (15)
  - Relative Strength (15)
- Daily snapshot pipeline and GitHub Actions schedule.
- Supabase persistence for watchlist, snapshots, and fundamentals cache.
- Read-only fallback mode for FMP rate-limit events (`429`).

## Reliability & Safety

- Market-closed fallback to latest valid snapshot.
- Stale quote indicator for data older than 24h.
- Missing PEG/FCF neutral fallback with no UI/pipeline crash.
- Correlation-ID based error logging for support triage.

## Testing & Quality Gates

- Unit, integration, and e2e test suites.
- Deterministic fixtures for OHLC/fundamentals.
- Unit-test no-live-network enforcement.
- CI matrix on Windows and Linux.
- Coverage report and threshold gate.

## Deployment Notes

- Streamlit Community Cloud deploy target: `app.py` on `main`.
- Required secrets:
  - `FMP_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`

## Known Operational Dependencies

- FMP API availability and quota.
- Supabase availability and valid credentials.
- GitHub Actions schedule health for daily pipeline runs.

## Post-Release Verification Checklist

- Production smoke test passes (dashboard, deep-dive, refresh).
- Mobile checks pass on iPhone and Android.
- A new snapshot appears after scheduled workflow run.
- Final regression suite remains green.
