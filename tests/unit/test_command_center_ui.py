from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app
from services.fmp_client import FMPRateLimitError, QuoteData
from services.yfinance_client import OhlcBar

pytestmark = pytest.mark.unit


@dataclass
class FakeRepository:
    watchlist: list[dict[str, Any]]
    snapshots: dict[str, list[dict[str, Any]]] | None = None

    def __post_init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {
            "MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08},
        }

    def watchlist_list(self) -> list[dict[str, Any]]:
        return list(self.watchlist)

    def watchlist_add(self, ticker: str) -> dict[str, Any]:
        existing = next((row for row in self.watchlist if row["ticker"] == ticker), None)
        if existing:
            return existing
        row = {"ticker": ticker}
        self.watchlist.append(row)
        return row

    def watchlist_remove(self, ticker: str) -> int:
        before = len(self.watchlist)
        self.watchlist = [row for row in self.watchlist if row["ticker"] != ticker]
        return before - len(self.watchlist)

    def fundamentals_cache_query(self, ticker: str) -> dict[str, Any] | None:
        return self.cache.get(ticker)

    def snapshot_query(self, ticker: str, limit: int = 90) -> list[dict[str, Any]]:
        rows = (self.snapshots or {}).get(ticker, [])
        return list(rows[:limit])


class FakeFMPClient:
    def __init__(self) -> None:
        self.read_only = False
        self.quote_cache_flags: list[bool] = []
        self.get_fundamentals_calls = 0
        self.get_cash_flow_calls = 0

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        self.quote_cache_flags.append(use_cache)
        return QuoteData(
            ticker=ticker,
            price=100.0,
            change_percent=1.0,
            year_high_52w=120.0,
            fetched_at=date(2026, 2, 26),  # type: ignore[arg-type]
        )

    def get_fundamentals(self, ticker: str) -> Any:
        self.get_fundamentals_calls += 1

        class Fundamentals:
            peg_ratio = 1.1

        return Fundamentals()

    def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> list[dict[str, Any]]:
        del ticker
        del limit
        self.get_cash_flow_calls += 1
        return [
            {"report_date": date(2025, 9, 30), "free_cash_flow": 1.0},
            {"report_date": date(2025, 12, 31), "free_cash_flow": 2.0},
            {"report_date": date(2026, 2, 1), "free_cash_flow": 3.0},
        ]


class FakeRateLimitedFMPClient(FakeFMPClient):
    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        del ticker
        del use_cache
        self.read_only = True
        raise FMPRateLimitError("rate limit")


class FakeYFinanceClient:
    def get_ohlc_2y(self, ticker: str) -> list[OhlcBar]:
        start = date(2025, 1, 1)
        bars: list[OhlcBar] = []
        for index in range(260):
            close = 80.0 + index * 0.2 + (0.5 if ticker == "SPY" else 0.0)
            bars.append(
                OhlcBar(
                    ticker=ticker,
                    date=start + timedelta(days=index),
                    open=close - 1,
                    high=close + 1,
                    low=close - 2,
                    close=close,
                    volume=1_000_000,
                )
            )
        return bars


def test_add_remove_ticker_flow_persists() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])

    added = app.add_ticker_to_watchlist(repo, " nvda ")
    removed_count = app.remove_ticker_from_watchlist(repo, "MSFT")

    assert added is True
    assert removed_count == 1
    assert [row["ticker"] for row in repo.watchlist_list()] == ["NVDA"]


def test_dashboard_rows_include_required_columns_and_indicators() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])
    fmp_client = FakeFMPClient()
    yfinance_client = FakeYFinanceClient()

    result = app.build_command_center_rows(
        repository=repo,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=False,
    )

    assert result.rows
    row = result.rows[0]
    assert set(row.keys()) == {"Ticker", "Price", "Price Gap %", "Monitor Meter", "Trend", "Deep Dive"}
    assert row["Ticker"] == "MSFT"
    assert row["Trend"] in {"🚀", "📉"}
    assert row["Monitor Meter"].startswith(("🟢", "🟠", "🔴"))


def test_manual_refresh_is_quote_first_and_skips_fundamentals() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])
    fmp_client = FakeFMPClient()
    yfinance_client = FakeYFinanceClient()

    app.build_command_center_rows(
        repository=repo,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=False,
    )
    app.build_command_center_rows(
        repository=repo,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=True,
    )

    assert fmp_client.quote_cache_flags == [True, False]
    assert fmp_client.get_fundamentals_calls == 1
    assert fmp_client.get_cash_flow_calls == 1


def test_read_only_mode_banner_flag_is_exposed() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])
    fmp_client = FakeRateLimitedFMPClient()
    yfinance_client = FakeYFinanceClient()

    result = app.build_command_center_rows(
        repository=repo,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=False,
    )

    assert result.read_only_mode is True
    assert result.rows[0]["Price"] == "N/A"


def test_local_latency_under_three_seconds_with_mocked_clients() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}, {"ticker": "NVDA"}, {"ticker": "AAPL"}])
    fmp_client = FakeFMPClient()
    yfinance_client = FakeYFinanceClient()

    start = perf_counter()
    result = app.build_command_center_rows(
        repository=repo,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        refresh_lite=True,
    )
    elapsed = perf_counter() - start

    assert len(result.rows) == 3
    assert elapsed < 3.0
