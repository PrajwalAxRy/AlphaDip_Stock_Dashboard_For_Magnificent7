from __future__ import annotations

from typing import Any

import pytest

import app
from deep_dive_ui import build_conviction_history_series, build_dynamic_commentary
from tests.conftest import FakeFMPClient, FakeRepository, FakeYFinanceClient

pytestmark = pytest.mark.unit



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
    repository = FakeRepository(
        watchlist=[{"ticker": "MSFT"}],
        snapshots={
            "MSFT": [
                {"date": "2026-02-03", "conviction_score": 58},
                {"date": "2026-02-01", "conviction_score": 52},
                {"date": "2026-02-02", "conviction_score": 55},
            ],
        },
        cache={"MSFT": {"peg_ratio": 1.2, "fcf_yield": 0.08}},
    )
    fmp_client = FakeFMPClient(price=112.0, year_high=140.0)
    yfinance_client = FakeYFinanceClient(base_close=95.0)

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
    repository = FakeRepository(
        watchlist=[{"ticker": "NVDA"}],
        snapshots={
            "NVDA": [{"date": "2026-02-02", "conviction_score": 49}],
        },
        cache={"NVDA": {"peg_ratio": None, "fcf_yield": None}},
    )
    fmp_client = FakeFMPClient(price=112.0, year_high=140.0, missing_fundamentals=True)
    yfinance_client = FakeYFinanceClient(base_close=95.0)

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
