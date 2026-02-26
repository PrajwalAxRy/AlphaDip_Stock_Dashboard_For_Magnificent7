from __future__ import annotations

from time import perf_counter
from typing import Any

import pytest

import app
from tests.conftest import (
    FakeFMPClient,
    FakeRateLimitedFMPClient,
    FakeRepository,
    FakeYFinanceClient,
)

pytestmark = pytest.mark.unit



def test_add_remove_ticker_flow_persists() -> None:
    repo = FakeRepository(
        watchlist=[{"ticker": "MSFT"}],
        cache={"MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08}},
    )

    added = app.add_ticker_to_watchlist(repo, " nvda ")
    removed_count = app.remove_ticker_from_watchlist(repo, "MSFT")

    assert added is True
    assert removed_count == 1
    assert [row["ticker"] for row in repo.watchlist_list()] == ["NVDA"]


def test_dashboard_rows_include_required_columns_and_indicators() -> None:
    repo = FakeRepository(
        watchlist=[{"ticker": "MSFT"}],
        cache={"MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08}},
    )
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
    repo = FakeRepository(
        watchlist=[{"ticker": "MSFT"}],
        cache={"MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08}},
    )
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
    repo = FakeRepository(
        watchlist=[{"ticker": "MSFT"}],
        cache={"MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08}},
    )
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
    repo = FakeRepository(
        watchlist=[{"ticker": "MSFT"}, {"ticker": "NVDA"}, {"ticker": "AAPL"}],
        cache={"MSFT": {"peg_ratio": 1.3, "fcf_yield": 0.08}},
    )
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
