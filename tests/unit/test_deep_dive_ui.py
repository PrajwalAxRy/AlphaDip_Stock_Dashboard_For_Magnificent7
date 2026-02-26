from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app
from deep_dive_ui import build_conviction_history_series, build_dynamic_commentary
from services.fmp_client import QuoteData
from services.yfinance_client import OhlcBar

pytestmark = pytest.mark.unit


@dataclass
class FakeRepository:
    watchlist: list[dict[str, Any]]

    def __post_init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {
            "MSFT": {"peg_ratio": 1.2, "fcf_yield": 0.08},
            "NVDA": {"peg_ratio": None, "fcf_yield": None},
        }
        self.snapshots: dict[str, list[dict[str, Any]]] = {
            "MSFT": [
                {"date": "2026-02-03", "conviction_score": 58},
                {"date": "2026-02-01", "conviction_score": 52},
                {"date": "2026-02-02", "conviction_score": 55},
            ],
            "NVDA": [
                {"date": "2026-02-02", "conviction_score": 49},
            ],
        }

    def fundamentals_cache_query(self, ticker: str) -> dict[str, Any] | None:
        return self.cache.get(ticker)

    def snapshot_query(self, ticker: str, limit: int = 90) -> list[dict[str, Any]]:
        rows = self.snapshots.get(ticker, [])
        return list(rows[:limit])


class FakeYFinanceClient:
    def get_ohlc_2y(self, ticker: str) -> list[OhlcBar]:
        start = date(2025, 1, 1)
        bars: list[OhlcBar] = []
        for index in range(260):
            close = 95.0 + index * 0.2 + (0.3 if ticker == "SPY" else 0.0)
            bars.append(
                OhlcBar(
                    ticker=ticker,
                    date=start,
                    open=close - 1,
                    high=close + 1,
                    low=close - 2,
                    close=close,
                    volume=1_000_000,
                )
            )
            start = date.fromordinal(start.toordinal() + 1)
        return bars


class FakeFMPClient:
    def __init__(self, *, missing_fundamentals: bool = False) -> None:
        self.read_only = False
        self.missing_fundamentals = missing_fundamentals

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        del use_cache
        return QuoteData(
            ticker=ticker,
            price=112.0,
            change_percent=0.8,
            year_high_52w=140.0,
            fetched_at=date(2026, 2, 26),  # type: ignore[arg-type]
        )

    def get_fundamentals(self, ticker: str) -> Any:
        del ticker

        class Fundamentals:
            peg_ratio = None if self.missing_fundamentals else 1.1

        return Fundamentals()

    def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> list[dict[str, Any]]:
        del ticker
        del limit
        if self.missing_fundamentals:
            return [
                {"report_date": date(2025, 9, 30), "free_cash_flow": None},
                {"report_date": date(2025, 12, 31), "free_cash_flow": None},
                {"report_date": date(2026, 2, 1), "free_cash_flow": None},
            ]
        return [
            {"report_date": date(2025, 9, 30), "free_cash_flow": 1.0},
            {"report_date": date(2025, 12, 31), "free_cash_flow": 2.0},
            {"report_date": date(2026, 2, 1), "free_cash_flow": 3.0},
        ]


def test_history_series_is_sorted_and_accurate() -> None:
    rows = [
        {"date": "2026-02-03", "conviction_score": 58},
        {"date": "2026-02-01", "conviction_score": 52},
        {"date": "2026-02-02", "conviction_score": 55},
    ]

    series = build_conviction_history_series(rows)

    assert [entry["Date"] for entry in series] == ["2026-02-01", "2026-02-02", "2026-02-03"]
    assert [entry["Conviction Score"] for entry in series] == [52, 55, 58]


def test_component_total_aligns_with_engine_output() -> None:
    repository = FakeRepository(watchlist=[{"ticker": "MSFT"}])
    fmp_client = FakeFMPClient()
    yfinance_client = FakeYFinanceClient()

    model = app.build_deep_dive_model(
        repository=repository,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        ticker="MSFT",
    )

    assert model is not None
    total_score = next(row["Score"] for row in model.component_rows if row["Component"] == "Total")
    assert int(round(float(total_score))) == model.conviction_score


def test_missing_fundamentals_sets_data_unavailable_and_does_not_crash() -> None:
    repository = FakeRepository(watchlist=[{"ticker": "NVDA"}])
    fmp_client = FakeFMPClient(missing_fundamentals=True)
    yfinance_client = FakeYFinanceClient()

    model = app.build_deep_dive_model(
        repository=repository,
        fmp_client=fmp_client,
        yfinance_client=yfinance_client,
        ticker="NVDA",
    )

    assert model is not None
    assert model.missing_fundamentals is True


def test_commentary_changes_by_score_profile() -> None:
    high = build_dynamic_commentary(
        conviction_score=82,
        monitor_meter_band="Strike Zone",
        is_recovery=True,
        missing_fundamentals=False,
    )
    low = build_dynamic_commentary(
        conviction_score=34,
        monitor_meter_band="Neutral",
        is_recovery=False,
        missing_fundamentals=True,
    )

    assert high != low
    assert "Strong setup" in high
    assert "Low-conviction setup" in low
    assert "Data Unavailable" in low
