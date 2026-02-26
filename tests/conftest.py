"""Shared test fixtures, fake clients, and factory functions.

This module consolidates duplicate fake/mock classes that were previously
defined independently across multiple test files.  All fakes match the
real interfaces in ``database.py``, ``services/fmp_client.py``, and
``services/yfinance_client.py``.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from services.fmp_client import (
    FMPRateLimitError,
    FundamentalsData,
    QuoteData,
)
from services.yfinance_client import OhlcBar


# ===================================================================
# Network-blocking guard — prevents accidental live calls in unit tests
# ===================================================================

_original_connect = socket.socket.connect


def _blocked_connect(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    raise OSError(
        "Unit tests must not make real network connections. "
        "Use a fake/mock instead."
    )


@pytest.fixture(autouse=True)
def _block_network_for_unit_tests(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatically block socket connections for tests marked ``unit``.

    Integration and e2e tests are unaffected.
    """
    markers = {m.name for m in request.node.iter_markers()}
    if "unit" in markers:
        monkeypatch.setattr(socket.socket, "connect", _blocked_connect)


# ===================================================================
# Shared Fake Classes
# ===================================================================


@dataclass
class FakeRepository:
    """In-memory fake matching the ``SupabaseRepository`` public API."""

    watchlist: list[dict[str, Any]] = field(default_factory=list)
    snapshots: dict[str, list[dict[str, Any]]] | None = None
    cache: dict[str, dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.snapshots is None:
            self.snapshots = {}
        if self.cache is None:
            self.cache = {}
        self.persisted_snapshots: list[dict[str, Any]] = []

    # -- watchlist ----------------------------------------------------------

    def watchlist_list(self) -> list[dict[str, Any]]:
        return list(self.watchlist)

    def watchlist_add(self, ticker: str) -> dict[str, Any]:
        existing = next(
            (row for row in self.watchlist if row["ticker"] == ticker),
            None,
        )
        if existing:
            return existing
        row = {"ticker": ticker}
        self.watchlist.append(row)
        return row

    def watchlist_remove(self, ticker: str) -> int:
        before = len(self.watchlist)
        self.watchlist = [r for r in self.watchlist if r["ticker"] != ticker]
        return before - len(self.watchlist)

    # -- snapshots ----------------------------------------------------------

    def snapshot_query(self, ticker: str, limit: int = 90) -> list[dict[str, Any]]:
        rows = (self.snapshots or {}).get(ticker, [])
        return list(rows[:limit])

    def snapshot_upsert(
        self,
        ticker: str,
        snapshot_date: str,
        price_gap: float,
        conviction_score: int,
        is_recovery: bool,
    ) -> dict[str, Any]:
        payload = {
            "ticker": ticker,
            "date": snapshot_date,
            "price_gap": price_gap,
            "conviction_score": conviction_score,
            "is_recovery": is_recovery,
        }
        existing = next(
            (
                r
                for r in self.persisted_snapshots
                if r["ticker"] == ticker and r["date"] == snapshot_date
            ),
            None,
        )
        if existing:
            existing.update(payload)
            return existing
        self.persisted_snapshots.append(payload)
        return payload

    # -- fundamentals cache -------------------------------------------------

    def fundamentals_cache_query(self, ticker: str) -> dict[str, Any] | None:
        return (self.cache or {}).get(ticker)

    def fundamentals_cache_upsert(
        self,
        ticker: str,
        as_of_date: str,
        peg_ratio: float | None,
        fcf_yield: float | None,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "ticker": ticker,
            "as_of_date": as_of_date,
            "peg_ratio": peg_ratio,
            "fcf_yield": fcf_yield,
            "raw_payload": raw_payload,
        }
        if self.cache is None:
            self.cache = {}
        self.cache[ticker] = payload
        return payload


class FakeFMPClient:
    """Normal FMP client fake returning valid, configurable data.

    Parameters
    ----------
    price : float
        Price returned by ``get_quote``.
    year_high : float
        52-week high returned by ``get_quote``.
    peg_ratio : float | None
        PEG ratio returned by ``get_fundamentals``.
    fcf : float | None
        FCF value per quarter returned by ``get_cash_flow_statement_quarter``.
    missing_fundamentals : bool
        If ``True``, fundamentals return ``None`` PEG and ``None`` FCF.
    """

    def __init__(
        self,
        *,
        price: float = 100.0,
        year_high: float = 120.0,
        peg_ratio: float | None = 1.1,
        fcf: float | None = 12_000_000_000.0,
        missing_fundamentals: bool = False,
    ) -> None:
        self.price = price
        self.year_high = year_high
        self.peg_ratio = None if missing_fundamentals else peg_ratio
        self.fcf = None if missing_fundamentals else fcf
        self.read_only = False
        # Call tracking
        self.get_quote_calls: list[str] = []
        self.quote_cache_flags: list[bool] = []
        self.get_fundamentals_calls: int = 0
        self.get_cash_flow_calls: int = 0

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        self.get_quote_calls.append(ticker)
        self.quote_cache_flags.append(use_cache)
        return QuoteData(
            ticker=ticker,
            price=self.price,
            change_percent=1.0,
            year_high_52w=self.year_high,
            fetched_at=datetime.now(timezone.utc),
        )

    def get_fundamentals(self, ticker: str, **kwargs: Any) -> FundamentalsData:
        self.get_fundamentals_calls += 1
        return FundamentalsData(
            ticker=ticker,
            peg_ratio=self.peg_ratio,
            free_cash_flow=self.fcf,
            fcf_report_date=date(2026, 2, 1) if self.fcf is not None else None,
            fetched_at=datetime.now(timezone.utc),
        )

    def get_cash_flow_statement_quarter(
        self, ticker: str, *, limit: int = 4
    ) -> list[dict[str, Any]]:
        self.get_cash_flow_calls += 1
        if self.fcf is None:
            return [
                {"ticker": ticker, "report_date": date(2025, 9, 30), "free_cash_flow": None},
                {"ticker": ticker, "report_date": date(2025, 12, 31), "free_cash_flow": None},
                {"ticker": ticker, "report_date": date(2026, 2, 1), "free_cash_flow": None},
            ]
        return [
            {"ticker": ticker, "report_date": date(2025, 9, 30), "free_cash_flow": 8_000_000_000.0},
            {"ticker": ticker, "report_date": date(2025, 12, 31), "free_cash_flow": 9_000_000_000.0},
            {"ticker": ticker, "report_date": date(2026, 2, 1), "free_cash_flow": 10_000_000_000.0},
        ]


class FakeRateLimitedFMPClient:
    """FMP client fake that always raises ``FMPRateLimitError``."""

    def __init__(self) -> None:
        self.read_only = True
        self.get_quote_calls: list[str] = []

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        self.get_quote_calls.append(ticker)
        raise FMPRateLimitError("rate limit")

    def get_fundamentals(self, ticker: str, **kwargs: Any) -> FundamentalsData:
        raise FMPRateLimitError("rate limit")

    def get_cash_flow_statement_quarter(
        self, ticker: str, *, limit: int = 4
    ) -> list[dict[str, Any]]:
        raise FMPRateLimitError("rate limit")


class FakeStaleFMPClient:
    """FMP client fake returning quotes fetched >24 h ago.

    Parameters
    ----------
    stale_at : datetime | None
        The ``fetched_at`` timestamp for all returned data.  Defaults to
        ``datetime(2026, 2, 22, 13, 0, tzinfo=timezone.utc)`` which is 30 h
        before the Monday 2026-02-23 19:00 UTC commonly used in tests.
    """

    def __init__(self, *, stale_at: datetime | None = None) -> None:
        self.read_only = False
        self.get_quote_calls: list[str] = []
        self._stale_at = stale_at or datetime(2026, 2, 22, 13, 0, tzinfo=timezone.utc)

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        self.get_quote_calls.append(ticker)
        return QuoteData(
            ticker=ticker,
            price=100.0,
            change_percent=1.0,
            year_high_52w=120.0,
            fetched_at=self._stale_at,
        )

    def get_fundamentals(self, ticker: str, **kwargs: Any) -> FundamentalsData:
        return FundamentalsData(
            ticker=ticker,
            peg_ratio=1.1,
            free_cash_flow=12_000_000_000.0,
            fcf_report_date=date(2026, 2, 1),
            fetched_at=self._stale_at,
        )

    def get_cash_flow_statement_quarter(
        self, ticker: str, *, limit: int = 4
    ) -> list[dict[str, Any]]:
        return [
            {"ticker": ticker, "report_date": date(2025, 9, 30), "free_cash_flow": 1.0},
            {"ticker": ticker, "report_date": date(2025, 12, 31), "free_cash_flow": 2.0},
            {"ticker": ticker, "report_date": date(2026, 2, 1), "free_cash_flow": 3.0},
        ]


class FakeYFinanceClient:
    """yfinance client fake generating deterministic OHLC bars.

    Parameters
    ----------
    base_close : float
        Starting close price for generated bars.
    bar_count : int
        Number of trading bars to generate.
    start_date : date
        First bar date.
    """

    def __init__(
        self,
        *,
        base_close: float = 80.0,
        bar_count: int = 260,
        start_date: date = date(2025, 1, 1),
    ) -> None:
        self.base_close = base_close
        self.bar_count = bar_count
        self.start_date = start_date

    def get_ohlc_2y(self, ticker: str) -> list[OhlcBar]:
        bars: list[OhlcBar] = []
        for i in range(self.bar_count):
            close = self.base_close + i * 0.2 + (0.5 if ticker == "SPY" else 0.0)
            bars.append(
                OhlcBar(
                    ticker=ticker,
                    date=self.start_date + timedelta(days=i),
                    open=close - 1,
                    high=close + 1,
                    low=close - 2,
                    close=close,
                    volume=1_000_000,
                )
            )
        return bars


# ===================================================================
# Factory helpers — use these to build deterministic test data
# ===================================================================


def make_ohlc_bars(
    ticker: str = "MSFT",
    *,
    base_close: float = 100.0,
    count: int = 260,
    start_date: date = date(2024, 3, 1),
) -> list[OhlcBar]:
    """Generate a deterministic OHLC bar series."""
    bars: list[OhlcBar] = []
    for i in range(count):
        close = base_close + i * 0.15
        bars.append(
            OhlcBar(
                ticker=ticker,
                date=start_date + timedelta(days=i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_500_000 + i * 100,
            )
        )
    return bars


def make_quote_data(
    ticker: str = "MSFT",
    *,
    price: float = 100.0,
    year_high: float = 120.0,
    change_percent: float = 1.0,
    fetched_at: datetime | None = None,
) -> QuoteData:
    """Build a deterministic ``QuoteData`` instance."""
    return QuoteData(
        ticker=ticker,
        price=price,
        change_percent=change_percent,
        year_high_52w=year_high,
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )


def make_fundamentals_data(
    ticker: str = "MSFT",
    *,
    peg_ratio: float | None = 1.5,
    fcf: float | None = 500_000_000.0,
    fetched_at: datetime | None = None,
) -> FundamentalsData:
    """Build a deterministic ``FundamentalsData`` instance."""
    return FundamentalsData(
        ticker=ticker,
        peg_ratio=peg_ratio,
        free_cash_flow=fcf,
        fcf_report_date=date(2026, 2, 1) if fcf is not None else None,
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )


def make_snapshot_row(
    ticker: str = "MSFT",
    *,
    date_str: str = "2026-02-26",
    price: float = 400.0,
    price_gap: float = 15.0,
    conviction_score: int = 70,
    is_recovery: bool = True,
) -> dict[str, Any]:
    """Build a deterministic snapshot row dict."""
    return {
        "ticker": ticker,
        "date": date_str,
        "price": price,
        "price_gap": price_gap,
        "conviction_score": conviction_score,
        "is_recovery": is_recovery,
    }


def make_fundamentals_cache_row(
    ticker: str = "MSFT",
    *,
    peg_ratio: float | None = 1.3,
    fcf_yield: float | None = 0.08,
) -> dict[str, Any]:
    """Build a deterministic fundamentals cache row dict."""
    return {"peg_ratio": peg_ratio, "fcf_yield": fcf_yield}


# ===================================================================
# Pytest fixtures returning pre-configured fakes
# ===================================================================


@pytest.fixture
def fake_repository() -> FakeRepository:
    """Repository with MSFT + AAPL watchlist and sample cached data."""
    return FakeRepository(
        watchlist=[{"ticker": "MSFT"}, {"ticker": "AAPL"}],
        snapshots={
            "MSFT": [make_snapshot_row("MSFT", date_str="2026-02-20", price_gap=12.5, conviction_score=62)],
            "AAPL": [make_snapshot_row("AAPL", date_str="2026-02-20", price=210.0, price_gap=8.0, conviction_score=45, is_recovery=False)],
        },
        cache={
            "MSFT": make_fundamentals_cache_row("MSFT"),
        },
    )


@pytest.fixture
def fake_fmp_client() -> FakeFMPClient:
    return FakeFMPClient()


@pytest.fixture
def fake_yfinance_client() -> FakeYFinanceClient:
    return FakeYFinanceClient()


@pytest.fixture
def fake_rate_limited_fmp() -> FakeRateLimitedFMPClient:
    return FakeRateLimitedFMPClient()


@pytest.fixture
def fake_stale_fmp() -> FakeStaleFMPClient:
    return FakeStaleFMPClient()
