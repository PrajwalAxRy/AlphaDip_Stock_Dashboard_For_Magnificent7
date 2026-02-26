from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cron_job import run_daily_snapshot_pipeline
from services.fmp_client import FundamentalsData, QuoteData
from services.yfinance_client import OhlcBar

pytestmark = pytest.mark.e2e


@dataclass
class FakeRepository:
    watchlist: List[Dict[str, str]]

    def __post_init__(self) -> None:
        self.snapshots: List[Dict[str, Any]] = []
        self.fundamentals_cache: Dict[str, Dict[str, Any]] = {}

    def watchlist_list(self) -> List[Dict[str, Any]]:
        return list(self.watchlist)

    def snapshot_upsert(
        self,
        ticker: str,
        snapshot_date: str,
        price_gap: float,
        conviction_score: int,
        is_recovery: bool,
    ) -> Dict[str, Any]:
        existing = next(
            (
                row
                for row in self.snapshots
                if row["ticker"] == ticker and row["date"] == snapshot_date
            ),
            None,
        )
        payload = {
            "ticker": ticker,
            "date": snapshot_date,
            "price_gap": price_gap,
            "conviction_score": conviction_score,
            "is_recovery": is_recovery,
        }
        if existing:
            existing.update(payload)
            return existing
        self.snapshots.append(payload)
        return payload

    def fundamentals_cache_upsert(
        self,
        ticker: str,
        as_of_date: str,
        peg_ratio: float | None,
        fcf_yield: float | None,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "ticker": ticker,
            "as_of_date": as_of_date,
            "peg_ratio": peg_ratio,
            "fcf_yield": fcf_yield,
            "raw_payload": raw_payload,
        }
        self.fundamentals_cache[ticker] = payload
        return payload

    def fundamentals_cache_query(self, ticker: str) -> Dict[str, Any] | None:
        return self.fundamentals_cache.get(ticker)


class FakeFMPClient:
    def __init__(self, quote_price: float = 120.0, year_high: float = 150.0) -> None:
        self.quote_price = quote_price
        self.year_high = year_high
        self.read_only = False

    def get_quote(self, ticker: str) -> QuoteData:
        return QuoteData(
            ticker=ticker,
            price=self.quote_price,
            change_percent=1.2,
            year_high_52w=self.year_high,
            fetched_at=datetime.now(timezone.utc),
        )

    def get_fundamentals(self, ticker: str) -> FundamentalsData:
        return FundamentalsData(
            ticker=ticker,
            peg_ratio=1.1,
            free_cash_flow=12_000_000_000.0,
            fcf_report_date=date(2026, 2, 1),
            fetched_at=datetime.now(timezone.utc),
        )

    def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> List[Dict[str, Any]]:
        del limit
        return [
            {"ticker": ticker, "report_date": date(2025, 9, 30), "free_cash_flow": 8_000_000_000.0},
            {"ticker": ticker, "report_date": date(2025, 12, 31), "free_cash_flow": 9_000_000_000.0},
            {"ticker": ticker, "report_date": date(2026, 2, 1), "free_cash_flow": 10_000_000_000.0},
        ]


class FakeYFinanceClient:
    def get_ohlc_2y(self, ticker: str) -> List[OhlcBar]:
        start = date(2025, 1, 1)
        bars: List[OhlcBar] = []
        for i in range(260):
            close = 100.0 + i * 0.2 + (0.5 if ticker == "SPY" else 0.0)
            bars.append(
                OhlcBar(
                    ticker=ticker,
                    date=start + timedelta(days=i),
                    open=close - 1.0,
                    high=close + 2.0,
                    low=close - 2.0,
                    close=close,
                    volume=1_000_000 + i,
                )
            )
        return bars


def test_pipeline_inserts_expected_snapshots_with_mocked_providers() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}, {"ticker": "NVDA"}])

    summary = run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(),
        yfinance_client=FakeYFinanceClient(),
    )

    assert summary.total_tickers == 2
    assert summary.processed == 2
    assert summary.persisted == 2
    assert summary.errors == 0

    assert len(repo.snapshots) == 2
    assert {row["ticker"] for row in repo.snapshots} == {"MSFT", "NVDA"}
    assert all(row["date"] == "2026-02-26" for row in repo.snapshots)


def test_pipeline_rerun_same_date_is_idempotent() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])

    run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(quote_price=125.0),
        yfinance_client=FakeYFinanceClient(),
    )
    run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(quote_price=130.0),
        yfinance_client=FakeYFinanceClient(),
    )

    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["ticker"] == "MSFT"
    assert repo.snapshots[0]["date"] == "2026-02-26"


def test_pipeline_dry_run_does_not_write_snapshots_or_cache() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "AAPL"}, {"ticker": "AMZN"}])

    summary = run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        dry_run=True,
        repository=repo,
        fmp_client=FakeFMPClient(),
        yfinance_client=FakeYFinanceClient(),
    )

    assert summary.persisted == 0
    assert summary.dry_run_skipped_writes == 2
    assert repo.snapshots == []
    assert repo.fundamentals_cache == {}
