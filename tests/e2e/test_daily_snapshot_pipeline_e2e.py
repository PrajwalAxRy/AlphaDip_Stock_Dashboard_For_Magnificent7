from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from cron_job import run_daily_snapshot_pipeline
from tests.conftest import FakeFMPClient, FakeRepository, FakeYFinanceClient

pytestmark = pytest.mark.e2e



def test_pipeline_inserts_expected_snapshots_with_mocked_providers() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}, {"ticker": "NVDA"}])

    summary = run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(price=120.0, year_high=150.0),
        yfinance_client=FakeYFinanceClient(base_close=100.0),
    )

    assert summary.total_tickers == 2
    assert summary.processed == 2
    assert summary.persisted == 2
    assert summary.errors == 0

    assert len(repo.persisted_snapshots) == 2
    assert {row["ticker"] for row in repo.persisted_snapshots} == {"MSFT", "NVDA"}
    assert all(row["date"] == "2026-02-26" for row in repo.persisted_snapshots)


def test_pipeline_rerun_same_date_is_idempotent() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "MSFT"}])

    run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(price=125.0, year_high=150.0),
        yfinance_client=FakeYFinanceClient(base_close=100.0),
    )
    run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        repository=repo,
        fmp_client=FakeFMPClient(price=130.0, year_high=150.0),
        yfinance_client=FakeYFinanceClient(base_close=100.0),
    )

    assert len(repo.persisted_snapshots) == 1
    assert repo.persisted_snapshots[0]["ticker"] == "MSFT"
    assert repo.persisted_snapshots[0]["date"] == "2026-02-26"


def test_pipeline_dry_run_does_not_write_snapshots_or_cache() -> None:
    repo = FakeRepository(watchlist=[{"ticker": "AAPL"}, {"ticker": "AMZN"}])

    summary = run_daily_snapshot_pipeline(
        as_of_date=date(2026, 2, 26),
        dry_run=True,
        repository=repo,
        fmp_client=FakeFMPClient(price=120.0, year_high=150.0),
        yfinance_client=FakeYFinanceClient(base_close=100.0),
    )

    assert summary.persisted == 0
    assert summary.dry_run_skipped_writes == 2
    assert repo.persisted_snapshots == []
    assert repo.cache == {}
