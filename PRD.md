# AlphaDip 2026 — Product Requirements Document (PRD)

## Part 1: Executive Summary & System Architecture

## 1) Product Overview

- **Project Name:** AlphaDip 2026
- **Vision:** A decision-support dashboard for long-term (2yr+) investors to identify high-quality entries in “safe-haven” tech stocks using a combination of price-gap analysis, fundamental health, and trend confirmation.
- **Target Platform:** Web-based (Streamlit), mobile-responsive.

## 2) Target Stocks (Initial Scope)

The system must support dynamic ticker entry but will be optimized for:

- **Big Tech:** MSFT, GOOGL, AMZN, META, AAPL, NVDA
- **High Beta Growth:** TSLA

## 3) High-Level System Architecture

The system follows a **Trigger → Monitor → Confirm** logic flow.

### Data Layer

- **FMP (Financial Modeling Prep):** Primary source for PEG, Free Cash Flow, and real-time quote.
- **yfinance:** Secondary source for 2-year historical daily OHLC (Open, High, Low, Close) data.

### Processing Layer (The “Engine”)

- A Python backend that calculates weighted scores and identifies **dips** vs. **recoveries**.

### Persistence Layer

- **Supabase (PostgreSQL):** Stores daily snapshots of the **Conviction Score** to enable historical trend charting.

### Presentation Layer

- **Streamlit** UI, deployed via **Streamlit Community Cloud**.

## 4) Technical Requirements & Logic (The “Algorithms”)

### A. The “Monitor Meter” (Signal 1: The Dip)

- **Logic:** Calculate % distance from 52-week high.
- **Thresholds:**
	- **0%–15%:** “Neutral” (Meter Score 1–3)
	- **15%–25%:** “Watching” (Meter Score 4–7)
	- **> 25%:** “Strike Zone” (Meter Score 8–10)

### B. The “Conviction Score” (Weighted Multi-Factor Model)

Final score range: **0–100**.

| Component | Weight | Logic / Calculation |
|---|---:|---|
| Price Architecture | 30% | If price is <30% from ATH, full points. Points decay as price approaches ATH. |
| Trend Confirmation | 20% | Binary: +20 points if price > 50-day moving average, else 0. |
| Growth Value (PEG) | 20% | Full points if PEG < 1.0, partial points up to 2.0, 0 points if > 2.0. |
| Cash Safety (FCF) | 15% | +15 points if FCF yield is positive and increasing over last 3 quarters. |
| Market Context (RS) | 15% | +15 points if stock 1-month return > S&P 500 1-month return (relative strength). |

## 5) Functional Requirements (User Actions)

- **U1 — Ticker Management:** User can add/remove tickers from a persistent watchlist.
- **U2 — Global Dashboard:** Table view showing all tracked tickers with current **Price Gap** and **Monitor Meter**.
- **U3 — Stock Deep-Dive:** Clicking a ticker opens a dedicated page with:
	- Historical **Conviction Score** chart (last 90 days)
	- Breakdown of the 5 component scores
	- Raw data (current P/E, PEG, FCF, 50-day MA)
- **U4 — Manual Refresh:** A button to force-pull new data from FMP/yfinance.

---

## Part 2: Data Engineering, Database Schema, and UI/UX

Continuing from the core architecture, this section details how data flows through the system and how users interact with the product.

## 6) Data Engineering & API Integration

### A. Data Fetching Strategy

To optimize for the FMP free tier (250 calls/day), the system must implement a caching layer.

- **Daily Cron Job:** A GitHub Action runs at **4:05 PM EST** (market close).
	- Fetches financial statements (FCF), ratios (PEG), and daily OHLC for all tickers in the database
	- Calculates final Conviction Score
	- Pushes results to the Supabase snapshot table
- **Real-Time “Lite” Refresh:** On app open, fetch only current price to update **Price Gap**. Read fundamentals from database to save API credits.

### B. Specific FMP Endpoints

- **Quote:** `/api/v3/quote/{ticker}` (price, change %, 52w high)
- **Financial Ratios:** `/api/v3/ratios-ttm/{ticker}` (PEG ratio)
- **Cash Flow Statement:** `/api/v3/cash-flow-statement/{ticker}?period=quarter` (free cash flow)

## 7) Database Schema (Supabase/PostgreSQL)

Implement the following three tables.

### Table 1: `watchlists`

| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| ticker | String | e.g., “MSFT”, “TSLA” |
| added_at | Timestamp | Date added |

### Table 2: `daily_snapshots` (The “Memory”)

| Column | Type | Description |
|---|---|---|
| id | BigInt | Primary key |
| ticker | String | Foreign key to `watchlists` |
| date | Date | Day of calculation |
| price_gap | Float | % below ATH |
| conviction_score | Integer | Calculated weighted score (0–100) |
| is_recovery | Boolean | True if price > 50d MA |

### Table 3: `fundamentals_cache`

- Stores quarterly data to prevent redundant API calls for data that only changes every 90 days.

## 8) UI/UX Specifications (Streamlit)

### A. View 1: “Command Center” (Main Dashboard)

- **Visual Element:** Search bar at top to add new tickers
- **List Layout:** `st.dataframe` or custom `st.columns`, showing:
	- Ticker & price
	- Monitor Meter (color-coded progress bar)
		- Green: <10% dip
		- Yellow: ~20% dip
		- Red/Purple: >30% dip
	- Trend indicator icon
		- 🚀 Recovery
		- 📉 Downtrend
	- “Deep Dive” button per row

### B. View 2: “Deep Dive” Page

- **Metric Gauges:** `st.metric` or Plotly gauge charts for 5 core signals (PEG, FCF, Price Gap, etc.)
- **History Chart:** `st.line_chart` of `conviction_score` over last 90 days
- **Analyst Commentary:** Dynamic `if/else` text summary, e.g.
	- “Price is at a deep discount, but PEG is high. Caution: this may be a value trap.”

## 9) Non-Functional Requirements

- **Security:** No hardcoded API keys. Use Streamlit secrets (`.streamlit/secrets.toml`) for FMP and Supabase credentials.
- **Latency:** Initial dashboard load should be <3 seconds.
- **Responsiveness:** All charts must use `use_container_width=True` for mobile compatibility.

---

## Part 3: Error Handling, Testing, and Deployment

This section defines safety rails so the app remains stable when data is missing or markets are closed.

## 10) Error Handling & Edge Cases

### A. Missing Fundamental Data

- **Scenario:** FMP returns null PEG ratio (common in high-volatility periods).
- **Requirement:** Algorithm must not crash. Assign neutral component score (e.g., 5/10) and display a **Data Unavailable** badge in deep-dive UI.

### B. Market Close / Weekends

- **Scenario:** User opens app on Sunday.
- **Requirement:** Show **Market Closed** status and use `daily_snapshots` from previous Friday. Do not attempt real-time quotes if timestamp is >24 hours old.

### C. API Rate Limiting

- **Scenario:** Multiple users refresh dashboard, exceeding FMP 250-call limit.
- **Requirement:** Implement a **circuit breaker**. On HTTP 429 (Too Many Requests), switch gracefully to **read-only** mode using only cached Supabase data.

## 11) Testing Protocols

Engineer must verify before hand-off:

- **Logic Verification:** Manually compute Conviction Score for one stock (e.g., MSFT) and confirm exact match with Python script output.
- **Mobile Stress Test:** Open Streamlit URL on iPhone and Android. Verify Monitor Meter readability and no horizontal table scrolling.
- **Persistence Test:** Add a stock, wait 24 hours, and verify a new point appears on historical Conviction Score chart.

## 12) Deployment Instructions (The “Hand-off”)

Project is complete once live on Streamlit Community Cloud.

### Step 1: GitHub Repository Structure

```text
/
├── .streamlit/
│   └── secrets.toml      # API Keys & DB Credentials (NOT pushed to Git)
├── app.py                # Main Streamlit UI
├── engine.py             # Logic for scoring & calculations
├── database.py           # Supabase connection & queries
├── requirements.txt      # streamlit, pandas, yfinance, requests, supabase
└── cron_job.py           # Script for GitHub Action updates
```

### Step 2: Environment Variables

Required Streamlit secrets:

- `FMP_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`

### Step 3: CI/CD Pipeline

Set up `.github/workflows/daily_update.yml` to automate the 4:05 PM EST data pull, ensuring historical charts remain up to date without manual intervention.

## 13) Summary of Deliverables

- **Source Code:** Clean, commented Python repository on GitHub
- **Database:** Live Supabase instance with specified schema
- **URL:** Public, functioning Streamlit app URL
- **Documentation:** Brief admin guide on updating Conviction Score weights as strategy changes