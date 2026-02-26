"""Milestone 8 tests — edge cases, reliability, and graceful degradation.

Covers:
  - Sunday simulation uses Friday snapshot and avoids live quote fetch.
  - 429 simulation keeps app usable in read-only mode.
  - Missing fundamentals never crash engine / UI / pipeline.
  - Stale-data status appears correctly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

import app
from cron_job import run_daily_snapshot_pipeline
from engine import build_conviction_result
from services.error_handling import (
    generate_correlation_id,
    is_quote_stale,
    log_error,
    log_warning,
    user_safe_message,
)
from services.fmp_client import FMPRateLimitError, FundamentalsData
from services.market_status import (
    is_market_closed,
    is_weekend,
    last_trading_date,
    should_skip_live_fetch,
)
from tests.conftest import (
    FakeFMPClient,
    FakeRateLimitedFMPClient,
    FakeRepository,
    FakeStaleFMPClient,
    FakeYFinanceClient,
    make_snapshot_row,
    make_fundamentals_cache_row,
)

pytestmark = pytest.mark.unit


# ===================================================================
# Helper: build pre-seeded FakeRepository for resilience tests
# ===================================================================


def _resilience_repo(
    tickers: list[str] | None = None,
) -> FakeRepository:
    """Return a ``FakeRepository`` pre-seeded for resilience tests."""
    if tickers is None:
        tickers = ["MSFT", "AAPL"]
    watchlist = [{"ticker": t} for t in tickers]
    snapshots = {
        "MSFT": [
            make_snapshot_row(
                "MSFT",
                date_str="2026-02-20",
                price_gap=12.5,
                conviction_score=62,
                is_recovery=True,
            ),
        ],
        "AAPL": [
            make_snapshot_row(
                "AAPL",
                date_str="2026-02-20",
                price=210.0,
                price_gap=8.0,
                conviction_score=45,
                is_recovery=False,
            ),
        ],
    }
    cache = {"MSFT": make_fundamentals_cache_row("MSFT")}
    return FakeRepository(watchlist=watchlist, snapshots=snapshots, cache=cache)


# ===================================================================
# Market Status Tests
# ===================================================================


class TestMarketStatus:
    """Tests for market_status module."""

    def test_saturday_is_weekend(self) -> None:
        assert is_weekend(date(2026, 2, 21)) is True  # Saturday

    def test_sunday_is_weekend(self) -> None:
        assert is_weekend(date(2026, 2, 22)) is True  # Sunday

    def test_friday_is_not_weekend(self) -> None:
        assert is_weekend(date(2026, 2, 20)) is False  # Friday

    def test_market_closed_on_sunday(self) -> None:
        assert is_market_closed(date(2026, 2, 22)) is True

    def test_market_open_on_weekday(self) -> None:
        assert is_market_closed(date(2026, 2, 23)) is False  # Monday

    def test_last_trading_date_from_sunday_is_friday(self) -> None:
        # Sunday 2026-02-22 -> last trading date = Friday 2026-02-20
        assert last_trading_date(date(2026, 2, 22)) == date(2026, 2, 20)

    def test_last_trading_date_on_weekday_returns_same(self) -> None:
        assert last_trading_date(date(2026, 2, 23)) == date(2026, 2, 23)

    def test_should_skip_live_fetch_on_sunday(self) -> None:
        sunday_et = datetime(2026, 2, 22, 14, 0, tzinfo=timezone.utc)
        assert should_skip_live_fetch(sunday_et) is True

    def test_should_not_skip_live_fetch_on_weekday(self) -> None:
        monday_afternoon = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)  # 14:00 ET
        assert should_skip_live_fetch(monday_afternoon) is False


# ===================================================================
# Error Handling Utility Tests
# ===================================================================


class TestErrorHandling:
    """Tests for error_handling module."""

    def test_correlation_id_is_unique(self) -> None:
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_user_safe_message_known_key(self) -> None:
        msg = user_safe_message("fmp_rate_limit")
        assert "rate limit" in msg.lower() or "unavailable" in msg.lower()

    def test_user_safe_message_unknown_key_returns_generic(self) -> None:
        msg = user_safe_message("nonexistent_key")
        assert "unexpected error" in msg.lower()

    def test_user_safe_message_with_correlation_id(self) -> None:
        msg = user_safe_message("unknown", correlation_id="abc123")
        assert "abc123" in msg

    def test_is_quote_stale_with_old_timestamp(self) -> None:
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        assert is_quote_stale(old) is True

    def test_is_quote_stale_with_recent_timestamp(self) -> None:
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        assert is_quote_stale(recent) is False

    def test_is_quote_stale_with_none(self) -> None:
        assert is_quote_stale(None) is True


# ===================================================================
# Sunday Simulation — uses Friday snapshot, avoids live quote fetch
# ===================================================================


class TestSundaySimulationUsesFridaySnapshot:
    """Sunday (market-closed) should serve cached rows, no FMP calls."""

    def test_sunday_command_center_uses_cached_snapshots(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        # Simulate Sunday afternoon UTC
        sunday_utc = datetime(2026, 2, 22, 18, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=sunday_utc,
        )

        assert result.market_closed is True
        assert len(result.rows) == 1
        # The row should come from the cached snapshot, not a live fetch
        assert result.rows[0]["Ticker"] == "MSFT"
        # FMP should NOT have been called
        assert len(fmp_client.get_quote_calls) == 0

    def test_sunday_renders_friday_data_for_multiple_tickers(self) -> None:
        repo = _resilience_repo(["MSFT", "AAPL"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        sunday_utc = datetime(2026, 2, 22, 18, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=sunday_utc,
        )

        assert result.market_closed is True
        assert len(result.rows) == 2
        assert result.rows[0]["Ticker"] == "MSFT"
        assert result.rows[1]["Ticker"] == "AAPL"
        # Should show cached data
        assert result.rows[0]["Trend"] == "🚀"  # is_recovery was True
        assert result.rows[1]["Trend"] == "📉"  # is_recovery was False
        # Zero FMP calls
        assert len(fmp_client.get_quote_calls) == 0

    def test_sunday_ticker_with_no_snapshot_shows_na(self) -> None:
        repo = _resilience_repo(["GOOG"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        sunday_utc = datetime(2026, 2, 22, 18, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=sunday_utc,
        )

        assert result.market_closed is True
        assert result.rows[0]["Price"] == "N/A"


# ===================================================================
# Pipeline weekend skip
# ===================================================================


class TestPipelineWeekendSkip:
    """Pipeline should skip processing when market is closed."""

    def test_pipeline_skips_on_sunday(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        summary = run_daily_snapshot_pipeline(
            as_of_date=date(2026, 2, 22),  # Sunday
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
        )

        assert summary.skipped_market_closed is True
        assert summary.total_tickers == 0
        assert summary.processed == 0
        assert summary.persisted == 0
        assert len(fmp_client.get_quote_calls) == 0

    def test_pipeline_skips_on_saturday(self) -> None:
        summary = run_daily_snapshot_pipeline(
            as_of_date=date(2026, 2, 21),  # Saturday
            repository=_resilience_repo(["MSFT"]),
            fmp_client=FakeFMPClient(),
            yfinance_client=FakeYFinanceClient(),
        )

        assert summary.skipped_market_closed is True

    def test_pipeline_runs_on_weekday(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        summary = run_daily_snapshot_pipeline(
            as_of_date=date(2026, 2, 23),  # Monday
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
        )

        assert summary.skipped_market_closed is False
        assert summary.processed == 1
        assert summary.persisted == 1


# ===================================================================
# 429 simulation — app usable in read-only mode
# ===================================================================


class TestRateLimitReadOnlyMode:
    """When FMP returns 429, app must stay usable with cached data."""

    def test_429_keeps_dashboard_usable_with_cached_data(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeRateLimitedFMPClient()
        yfinance_client = FakeYFinanceClient()

        # Weekday time
        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        assert result.read_only_mode is True
        assert len(result.rows) == 1
        # Should have fallen back to cached snapshot
        row = result.rows[0]
        assert row["Ticker"] == "MSFT"
        # The row should use cached snapshot data
        assert row["Trend"] == "🚀"  # from cached is_recovery=True

    def test_429_read_only_mode_flag_is_true(self) -> None:
        repo = _resilience_repo(["AAPL"])
        fmp_client = FakeRateLimitedFMPClient()
        yfinance_client = FakeYFinanceClient()

        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        assert result.read_only_mode is True

    def test_429_ticker_without_cached_snapshot_shows_na(self) -> None:
        repo = _resilience_repo(["GOOG"])
        fmp_client = FakeRateLimitedFMPClient()
        yfinance_client = FakeYFinanceClient()

        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        # GOOG has no cached snapshot, so N/A is expected
        assert result.rows[0]["Price"] == "N/A"


# ===================================================================
# Missing fundamentals never crash engine / UI / pipeline
# ===================================================================


class TestMissingFundamentalsNeverCrash:
    """Engine, UI, and pipeline must handle missing PEG/FCF gracefully."""

    def test_engine_with_all_none_fundamentals(self) -> None:
        result = build_conviction_result(
            current_price=95.0,
            high_52_week=100.0,
            ma_50_day=100.0,
            peg_ratio=None,
            fcf_yield_last_3_quarters=None,
            stock_return_1m=None,
            sp500_return_1m=None,
        )
        # Should not crash and use neutral fallbacks
        assert 0 <= result.conviction_score <= 100
        assert result.components.peg == 10.0   # neutral for PEG_WEIGHT=20
        assert result.components.fcf_safety == 7.5  # neutral for FCF_WEIGHT=15

    def test_engine_with_none_in_fcf_series(self) -> None:
        result = build_conviction_result(
            current_price=95.0,
            high_52_week=100.0,
            ma_50_day=100.0,
            peg_ratio=1.5,
            fcf_yield_last_3_quarters=[None, 0.02, None],
            stock_return_1m=0.01,
            sp500_return_1m=0.02,
        )
        assert 0 <= result.conviction_score <= 100
        assert result.components.fcf_safety == 7.5  # neutral fallback

    def test_engine_with_empty_fcf_series(self) -> None:
        result = build_conviction_result(
            current_price=95.0,
            high_52_week=100.0,
            ma_50_day=100.0,
            peg_ratio=1.0,
            fcf_yield_last_3_quarters=[],
            stock_return_1m=0.01,
            sp500_return_1m=0.02,
        )
        assert 0 <= result.conviction_score <= 100
        assert result.components.fcf_safety == 7.5

    def test_pipeline_with_missing_fundamentals_does_not_crash(self) -> None:
        """Pipeline should process ticker successfully even if fundamentals are missing."""

        class NoFundamentalsFMP(FakeFMPClient):
            def get_fundamentals(self, ticker: str) -> FundamentalsData:
                return FundamentalsData(
                    ticker=ticker,
                    peg_ratio=None,
                    free_cash_flow=None,
                    fcf_report_date=None,
                    fetched_at=datetime.now(timezone.utc),
                )

            def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> list[dict[str, Any]]:
                return []

        repo = _resilience_repo(["MSFT"])

        summary = run_daily_snapshot_pipeline(
            as_of_date=date(2026, 2, 23),  # Monday
            repository=repo,
            fmp_client=NoFundamentalsFMP(),
            yfinance_client=FakeYFinanceClient(),
        )

        assert summary.errors == 0
        assert summary.processed == 1

    def test_ui_build_deep_dive_missing_fundamentals_no_crash(self) -> None:
        """Deep-dive model should build even when fundamentals are all None."""

        class NullFundamentalsFMP(FakeFMPClient):
            def get_fundamentals(self, ticker: str) -> Any:
                class F:
                    peg_ratio = None
                return F()

            def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> list[dict[str, Any]]:
                return [
                    {"report_date": date(2025, 9, 30), "free_cash_flow": None},
                    {"report_date": date(2025, 12, 31), "free_cash_flow": None},
                    {"report_date": date(2026, 2, 1), "free_cash_flow": None},
                ]

        repo = _resilience_repo(["MSFT"])
        model = app.build_deep_dive_model(
            repository=repo,
            fmp_client=NullFundamentalsFMP(),
            yfinance_client=FakeYFinanceClient(),
            ticker="MSFT",
        )

        assert model is not None
        assert model.missing_fundamentals is True
        assert 0 <= model.conviction_score <= 100


# ===================================================================
# Stale-data status appears correctly
# ===================================================================


class TestStaleDataStatus:
    """Stale quotes (>24h) should be flagged in the command center result."""

    def test_stale_quote_is_flagged(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeStaleFMPClient()
        yfinance_client = FakeYFinanceClient()

        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        assert result.stale_tickers == ["MSFT"]

    def test_fresh_quote_is_not_flagged(self) -> None:
        repo = _resilience_repo(["MSFT"])
        fmp_client = FakeFMPClient()
        yfinance_client = FakeYFinanceClient()

        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        assert result.stale_tickers == []

    def test_multiple_stale_tickers_all_flagged(self) -> None:
        repo = _resilience_repo(["MSFT", "AAPL"])
        fmp_client = FakeStaleFMPClient()
        yfinance_client = FakeYFinanceClient()

        monday_utc = datetime(2026, 2, 23, 19, 0, tzinfo=timezone.utc)

        result = app.build_command_center_rows(
            repository=repo,
            fmp_client=fmp_client,
            yfinance_client=yfinance_client,
            refresh_lite=False,
            now=monday_utc,
        )

        assert set(result.stale_tickers) == {"MSFT", "AAPL"}


# ===================================================================
# Hardened null payload handling — providers
# ===================================================================


class TestHardenedNullPayloads:
    """Provider clients should survive malformed / null payloads."""

    def test_engine_zero_high_52w_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_conviction_result(
                current_price=100.0,
                high_52_week=0.0,
                ma_50_day=100.0,
                peg_ratio=1.1,
                fcf_yield_last_3_quarters=[1.0, 2.0, 3.0],
                stock_return_1m=0.01,
                sp500_return_1m=0.02,
            )

    def test_engine_negative_price_gap_is_clamped_to_zero(self) -> None:
        """If current_price > high_52_week, gap should be clamped to 0."""
        result = build_conviction_result(
            current_price=150.0,
            high_52_week=100.0,
            ma_50_day=100.0,
            peg_ratio=1.0,
            fcf_yield_last_3_quarters=[1.0, 2.0, 3.0],
            stock_return_1m=0.01,
            sp500_return_1m=0.02,
        )
        assert result.price_gap_percent == 0.0
