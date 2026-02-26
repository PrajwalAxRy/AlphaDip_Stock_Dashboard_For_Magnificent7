# AlphaDip UAT Checklist (Milestone 10)

## Environment

- App URL: `TBD_PUBLIC_STREAMLIT_URL`
- Build/Commit: `TBD`
- Date Window: `TBD`
- Testers: `TBD`

## Pass/Fail Convention

- Mark each scenario as `PASS`, `FAIL`, or `BLOCKED`.
- Add evidence (screenshots, logs, workflow run links).
- Do not mark Milestone 10 complete until all required scenarios are `PASS`.

---

## 1) Logic Verification (PRD alignment)

### 1.1 Conviction Score Integrity

- [ ] Confirm score always stays in `0-100`.
- [ ] Confirm `is_recovery` is true only when `price > 50d MA`.
- [ ] Confirm missing PEG/FCF does not crash UI and uses neutral fallback.
- [ ] Confirm monitor meter labels align with score bands.

Evidence:

- [ ] Screenshot of dashboard values
- [ ] Screenshot of deep-dive component breakdown

### 1.2 Deep Dive Integrity

- [ ] 90-day conviction history renders sorted by date.
- [ ] Component totals match overall conviction output.
- [ ] Commentary text changes across low/medium/high score profiles.

Evidence:

- [ ] Screenshot of 90-day chart
- [ ] Screenshot of commentary for at least 2 different profiles

---

## 2) Mobile Stress Test

Devices:

- [ ] iPhone (Safari)
- [ ] Android (Chrome)

Checks:

- [ ] No horizontal overflow in Command Center.
- [ ] No horizontal overflow in Deep Dive.
- [ ] Table/metric readability is acceptable without clipped labels.
- [ ] Buttons and ticker interactions are usable (tap targets work).

Evidence:

- [ ] iPhone screenshots
- [ ] Android screenshots

---

## 3) Persistence Over 24 Hours

### 3.1 Scheduled Workflow

- [ ] Confirm `.github/workflows/daily_update.yml` scheduled run executes.
- [ ] Confirm run uses configured production secrets.
- [ ] Confirm no workflow execution failure.

### 3.2 Snapshot Validation

- [ ] New snapshot appears after next scheduled run.
- [ ] Snapshot row count does not duplicate on same-day rerun.
- [ ] Dashboard/deep-dive reflect newest persisted date.

Evidence:

- [ ] Link to Actions run
- [ ] DB evidence (query output or admin screenshot)

---

## 4) Production Smoke Test

- [ ] Dashboard loads
- [ ] Deep-dive opens for a ticker
- [ ] Manual refresh succeeds
- [ ] No critical exception on first load

---

## 5) Final Sign-off

- [ ] All Milestone 10 production checks pass
- [ ] Final regression suite passes unchanged
- [ ] Admin guide reviewed by handoff owner
- [ ] Release tag created (`v1.0.0`)

Approver: `TBD`

Date: `TBD`
