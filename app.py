from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Any, Iterable, List, Sequence

import streamlit as st

from database import SupabaseRepository
from deep_dive_ui import (
    DeepDiveRenderModel,
    build_conviction_history_series,
    build_dynamic_commentary,
    is_fundamentals_data_unavailable,
    render_deep_dive_page,
)
from engine import build_conviction_result
from services.cache import AlphaDipCachePolicy
from services.fmp_client import FMPClient, FMPClientError, FMPRateLimitError
from services.yfinance_client import OhlcBar, YFinanceClient, YFinanceClientError
from ui_helpers import monitor_meter_label


REQUIRED_SECRETS = ["FMP_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
TRADING_DAYS_1M = 21
TRADING_DAYS_1Y = 252


@dataclass(frozen=True)
class CommandCenterResult:
    rows: list[dict[str, Any]]
    read_only_mode: bool


def get_missing_secrets(required_keys: List[str]) -> List[str]:
    try:
        secrets = st.secrets
    except Exception:
        return required_keys

    missing = []
    for key in required_keys:
        value = secrets.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    return missing


def add_ticker_to_watchlist(repository: Any, ticker: str) -> bool:
    normalized = ticker.strip().upper()
    if not normalized:
        return False
    repository.watchlist_add(normalized)
    return True


def remove_ticker_from_watchlist(repository: Any, ticker: str) -> int:
    normalized = ticker.strip().upper()
    if not normalized:
        return 0
    return int(repository.watchlist_remove(normalized))


def should_show_read_only_banner(fmp_client: Any) -> bool:
    return bool(getattr(fmp_client, "read_only", False))


def build_command_center_rows(
    *,
    repository: Any,
    fmp_client: Any,
    yfinance_client: Any,
    refresh_lite: bool,
) -> CommandCenterResult:
    watchlist = repository.watchlist_list()
    tickers = [
        str(row.get("ticker", "")).strip().upper()
        for row in watchlist
        if str(row.get("ticker", "")).strip()
    ]

    benchmark_return_1m = _safe_benchmark_return(yfinance_client)
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        row: dict[str, Any] = {
            "Ticker": ticker,
            "Price": "N/A",
            "Price Gap %": "N/A",
            "Monitor Meter": "N/A",
            "Trend": "📉",
            "Deep Dive": f"Open {ticker}",
        }

        try:
            quote = fmp_client.get_quote(ticker, use_cache=not refresh_lite)
            bars = yfinance_client.get_ohlc_2y(ticker)
            ma_50_day = _compute_ma_50(bars, quote.price)
            high_52_week = (
                quote.year_high_52w
                if quote.year_high_52w and quote.year_high_52w > 0
                else _compute_high_52w(bars, quote.price)
            )
            stock_return_1m = _compute_one_month_return(bars)
            peg_ratio, fcf_series = _resolve_peg_and_fcf(
                repository=repository,
                fmp_client=fmp_client,
                ticker=ticker,
                refresh_lite=refresh_lite,
            )

            conviction = build_conviction_result(
                current_price=quote.price,
                high_52_week=high_52_week,
                ma_50_day=ma_50_day,
                peg_ratio=peg_ratio,
                fcf_yield_last_3_quarters=fcf_series,
                stock_return_1m=stock_return_1m,
                sp500_return_1m=benchmark_return_1m,
            )

            row = {
                "Ticker": ticker,
                "Price": round(quote.price, 2),
                "Price Gap %": conviction.price_gap_percent,
                "Monitor Meter": monitor_meter_label(
                    conviction.monitor_meter_band,
                    conviction.monitor_meter_score,
                ),
                "Trend": "🚀" if conviction.is_recovery else "📉",
                "Deep Dive": f"Open {ticker}",
            }
        except (FMPRateLimitError, FMPClientError, YFinanceClientError, ValueError):
            pass

        rows.append(row)

    return CommandCenterResult(rows=rows, read_only_mode=should_show_read_only_banner(fmp_client))


def build_deep_dive_model(
    *,
    repository: Any,
    fmp_client: Any,
    yfinance_client: Any,
    ticker: str,
) -> DeepDiveRenderModel | None:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return None

    try:
        quote = fmp_client.get_quote(normalized_ticker, use_cache=True)
        bars = yfinance_client.get_ohlc_2y(normalized_ticker)
        ma_50_day = _compute_ma_50(bars, quote.price)
        high_52_week = (
            quote.year_high_52w
            if quote.year_high_52w and quote.year_high_52w > 0
            else _compute_high_52w(bars, quote.price)
        )
        stock_return_1m = _compute_one_month_return(bars)
        benchmark_return_1m = _safe_benchmark_return(yfinance_client)
        peg_ratio, fcf_series = _resolve_peg_and_fcf(
            repository=repository,
            fmp_client=fmp_client,
            ticker=normalized_ticker,
            refresh_lite=False,
        )

        conviction = build_conviction_result(
            current_price=quote.price,
            high_52_week=high_52_week,
            ma_50_day=ma_50_day,
            peg_ratio=peg_ratio,
            fcf_yield_last_3_quarters=fcf_series,
            stock_return_1m=stock_return_1m,
            sp500_return_1m=benchmark_return_1m,
        )

        snapshots = repository.snapshot_query(normalized_ticker, limit=90)
        conviction_history = build_conviction_history_series(snapshots)
        missing_fundamentals = is_fundamentals_data_unavailable(peg_ratio, fcf_series)

        components = conviction.components
        component_rows = [
            {"Component": "Price Architecture", "Score": round(components.price_architecture, 2), "Weight": 30},
            {"Component": "Trend Confirmation", "Score": round(components.trend_confirmation, 2), "Weight": 20},
            {"Component": "PEG", "Score": round(components.peg, 2), "Weight": 20},
            {"Component": "FCF Safety", "Score": round(components.fcf_safety, 2), "Weight": 15},
            {"Component": "Relative Strength", "Score": round(components.relative_strength, 2), "Weight": 15},
            {"Component": "Total", "Score": round(components.total, 2), "Weight": 100},
        ]

        fcf_values = list(fcf_series[:3]) if fcf_series else [None, None, None]
        while len(fcf_values) < 3:
            fcf_values.append(None)

        raw_metric_rows = [
            {"Metric": "Current Price", "Value": round(quote.price, 2)},
            {"Metric": "Price Gap %", "Value": conviction.price_gap_percent},
            {
                "Metric": "Monitor Meter",
                "Value": f"{conviction.monitor_meter_band} ({conviction.monitor_meter_score}/10)",
            },
            {"Metric": "Is Recovery", "Value": conviction.is_recovery},
            {"Metric": "50D MA", "Value": round(ma_50_day, 2)},
            {"Metric": "52W High", "Value": round(high_52_week, 2)},
            {"Metric": "PEG Ratio", "Value": peg_ratio if peg_ratio is not None else "N/A"},
            {"Metric": "FCF Q1", "Value": fcf_values[0] if fcf_values[0] is not None else "N/A"},
            {"Metric": "FCF Q2", "Value": fcf_values[1] if fcf_values[1] is not None else "N/A"},
            {"Metric": "FCF Q3", "Value": fcf_values[2] if fcf_values[2] is not None else "N/A"},
            {
                "Metric": "Stock 1M Return",
                "Value": round(stock_return_1m, 4) if stock_return_1m is not None else "N/A",
            },
            {
                "Metric": "S&P 1M Return",
                "Value": round(benchmark_return_1m, 4) if benchmark_return_1m is not None else "N/A",
            },
        ]

        commentary = build_dynamic_commentary(
            conviction_score=conviction.conviction_score,
            monitor_meter_band=conviction.monitor_meter_band,
            is_recovery=conviction.is_recovery,
            missing_fundamentals=missing_fundamentals,
        )

        return DeepDiveRenderModel(
            ticker=normalized_ticker,
            conviction_score=conviction.conviction_score,
            conviction_history=conviction_history,
            component_rows=component_rows,
            raw_metric_rows=raw_metric_rows,
            commentary=commentary,
            missing_fundamentals=missing_fundamentals,
        )
    except (FMPRateLimitError, FMPClientError, YFinanceClientError, ValueError):
        return None


def _compute_ma_50(bars: Sequence[OhlcBar], fallback_price: float) -> float:
    if not bars:
        return fallback_price
    closes = [bar.close for bar in bars[-50:] if bar.close is not None]
    if not closes:
        return fallback_price
    return float(mean(closes))


def _compute_high_52w(bars: Sequence[OhlcBar], fallback_price: float) -> float:
    if not bars:
        return fallback_price
    highs = [bar.high for bar in bars[-TRADING_DAYS_1Y:] if bar.high is not None and bar.high > 0]
    if not highs:
        return fallback_price
    return float(max(highs))


def _compute_one_month_return(bars: Sequence[OhlcBar]) -> float | None:
    if len(bars) <= TRADING_DAYS_1M:
        return None
    latest_close = bars[-1].close
    month_ago_close = bars[-(TRADING_DAYS_1M + 1)].close
    if month_ago_close == 0:
        return None
    return (latest_close - month_ago_close) / month_ago_close


def _safe_benchmark_return(yfinance_client: Any) -> float | None:
    try:
        spy_bars = yfinance_client.get_ohlc_2y("SPY")
        return _compute_one_month_return(spy_bars)
    except YFinanceClientError:
        return None


def _to_chronological_fcf_series(cash_flows: Iterable[dict[str, Any]]) -> list[float | None]:
    def _sort_key(row: dict[str, Any]) -> date:
        raw = row.get("report_date")
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return date.fromisoformat(raw)
            except ValueError:
                return date.min
        return date.min

    ordered = sorted(cash_flows, key=_sort_key)
    return [row.get("free_cash_flow") for row in ordered[-3:]]


def _resolve_peg_and_fcf(
    *,
    repository: Any,
    fmp_client: Any,
    ticker: str,
    refresh_lite: bool,
) -> tuple[float | None, Sequence[float | None] | None]:
    if refresh_lite:
        cached = repository.fundamentals_cache_query(ticker)
        peg_ratio = cached.get("peg_ratio") if cached else None
        cached_fcf = cached.get("fcf_yield") if cached else None
        fcf_series = [cached_fcf, cached_fcf, cached_fcf] if cached_fcf is not None else None
        return peg_ratio, fcf_series

    try:
        fundamentals = fmp_client.get_fundamentals(ticker)
        cash_flows = fmp_client.get_cash_flow_statement_quarter(ticker)
        return fundamentals.peg_ratio, _to_chronological_fcf_series(cash_flows)
    except FMPRateLimitError:
        cached = repository.fundamentals_cache_query(ticker)
        peg_ratio = cached.get("peg_ratio") if cached else None
        cached_fcf = cached.get("fcf_yield") if cached else None
        fcf_series = [cached_fcf, cached_fcf, cached_fcf] if cached_fcf is not None else None
        return peg_ratio, fcf_series


def _build_clients() -> tuple[SupabaseRepository | None, FMPClient | None, YFinanceClient | None]:
    try:
        repository = SupabaseRepository.from_config(config=dict(st.secrets))
        fmp_client = FMPClient(
            api_key=str(st.secrets.get("FMP_API_KEY", "")),
            cache_policy=AlphaDipCachePolicy(),
        )
        yfinance_client = YFinanceClient()
        return repository, fmp_client, yfinance_client
    except Exception:
        return None, None, None


def render_command_center_view() -> None:
    st.subheader("Command Center")

    repository, fmp_client, yfinance_client = _build_clients()
    if repository is None or fmp_client is None or yfinance_client is None:
        st.error("Unable to initialize data clients. Verify Streamlit secrets and connectivity.")
        return

    manage_col, refresh_col = st.columns([3, 1])
    with manage_col:
        with st.form("watchlist_add_form", clear_on_submit=True):
            ticker_input = st.text_input("Add ticker", placeholder="MSFT")
            submitted = st.form_submit_button("Add")
            if submitted:
                if add_ticker_to_watchlist(repository, ticker_input):
                    st.success(f"Added {ticker_input.strip().upper()} to watchlist")
                else:
                    st.warning("Enter a valid ticker symbol")

    refresh_lite = False
    with refresh_col:
        refresh_lite = st.button("Manual Refresh", use_container_width=True)
        if refresh_lite:
            st.caption("Lite refresh: quote-first update")

    watchlist = repository.watchlist_list()
    tickers = [row["ticker"] for row in watchlist if row.get("ticker")]
    if tickers:
        remove_ticker = st.selectbox("Remove ticker", options=tickers)
        if st.button("Remove Selected", use_container_width=True):
            removed = remove_ticker_from_watchlist(repository, remove_ticker)
            if removed > 0:
                st.success(f"Removed {remove_ticker}")
            else:
                st.warning(f"Ticker {remove_ticker} not found")

    result = build_command_center_rows(
        repository=repository,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=refresh_lite,
    )

    if result.read_only_mode:
        st.warning("Read-only mode active: FMP rate limit circuit breaker is enabled.")

    if not result.rows:
        st.info("No tickers in watchlist. Add one to begin monitoring.")
        return

    st.dataframe(result.rows, use_container_width=True)

    st.markdown("### Deep Dive")
    for row in result.rows:
        ticker = row["Ticker"]
        if st.button(f"Open {ticker}", key=f"deep_dive_{ticker}", use_container_width=True):
            st.session_state["selected_ticker"] = ticker
            st.session_state["active_view"] = "deep_dive"
            st.rerun()


def render_deep_dive_view(ticker: str) -> None:
    repository, fmp_client, yfinance_client = _build_clients()
    if repository is None or fmp_client is None or yfinance_client is None:
        st.error("Unable to initialize data clients. Verify Streamlit secrets and connectivity.")
        return

    model = build_deep_dive_model(
        repository=repository,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        ticker=ticker,
    )

    if model is None:
        st.error(f"Unable to load deep-dive data for {ticker}.")
        if st.button("← Back to Command Center", use_container_width=True):
            st.session_state["active_view"] = "command_center"
            st.session_state.pop("selected_ticker", None)
            st.rerun()
        return

    if render_deep_dive_page(model):
        st.session_state["active_view"] = "command_center"
        st.session_state.pop("selected_ticker", None)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="AlphaDip 2026", layout="wide")
    st.title("AlphaDip 2026")
    st.caption("Trigger → Monitor → Confirm")

    missing = get_missing_secrets(REQUIRED_SECRETS)
    if missing:
        st.error(
            "Missing required Streamlit secrets: "
            + ", ".join(missing)
            + ". Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill values."
        )
        return

    active_view = str(st.session_state.get("active_view", "command_center"))
    if active_view == "deep_dive":
        selected_ticker = str(st.session_state.get("selected_ticker", "")).strip().upper()
        if selected_ticker:
            render_deep_dive_view(selected_ticker)
            return
        st.session_state["active_view"] = "command_center"

    render_command_center_view()


if __name__ == "__main__":
    main()
