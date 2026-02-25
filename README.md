# AlphaDip 2026

Baseline scaffold for the AlphaDip stock monitor.

## Quick Start

1. Activate the virtual environment:
   - PowerShell: `./AlphDipVenv/Scripts/Activate.ps1`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Create local secrets file:
   - Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   - Fill `FMP_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
4. Run tests:
   - `pytest -q`
5. Run app:
   - `streamlit run app.py`

If secrets are missing, the app shows a clear error message and does not crash.


## Validation
1. python -m pytest -q → 2 passed.
2. python -m streamlit run [app.py](http://_vscodecontentref_/13) --server.headless true --browser.gatherUsageStats false --server.port 8510 started successfully and reported local URL.