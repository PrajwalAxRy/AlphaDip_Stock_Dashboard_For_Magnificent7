from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from statistics import mean
from typing import Any, Iterable, Sequence

from database import SupabaseRepository
from engine import build_conviction_result
from services.error_handling import log_error, log_warning
from services.fmp_client import FMPClient, FMPClientError, FMPRateLimitError
from services.market_status import is_market_closed, last_trading_date
from services.yfinance_client import OhlcBar, YFinanceClient, YFinanceClientError


LOGGER = logging.getLogger(__name__)
TRADING_DAYS_1M = 21
TRADING_DAYS_1Y = 252


@dataclass(frozen=True)
class PipelineSummary:
    run_date: str
    total_tickers: int
    processed: int
    persisted: int
    dry_run_skipped_writes: int
    errors: int
    read_only_mode: bool
    skipped_market_closed: bool = False


def run_daily_snapshot_pipeline(
    *,
    as_of_date: date | None = None,
    dry_run: bool = False,
    repository: SupabaseRepository | None = None,
    fmp_client: FMPClient | None = None,
    yfinance_client: YFinanceClient | None = None,
) -> PipelineSummary:
    run_date = as_of_date or date.today()

    # --- Weekend / market-closed guard ---
    if is_market_closed(run_date):
        LOGGER.info(
            "pipeline_skipped_market_closed run_date=%s last_trading_date=%s",
            run_date.isoformat(),
            last_trading_date(run_date).isoformat(),
        )
        return PipelineSummary(
            run_date=run_date.isoformat(),
            total_tickers=0,
            processed=0,
            persisted=0,
            dry_run_skipped_writes=0,
            errors=0,
            read_only_mode=False,
            skipped_market_closed=True,
        )

    repo = repository or SupabaseRepository.from_config()
    fmp = fmp_client or FMPClient(api_key=_load_fmp_api_key())
    yfinance = yfinance_client or YFinanceClient()

    watchlist_rows = repo.watchlist_list()
    tickers = [
        str(row.get("ticker", "")).strip().upper()
        for row in watchlist_rows
        if str(row.get("ticker", "")).strip()
    ]
    benchmark_return_1m = _safe_benchmark_return(yfinance)

    processed = 0
    persisted = 0
    dry_run_skipped_writes = 0
    errors = 0

    LOGGER.info(
        "pipeline_start run_date=%s dry_run=%s total_tickers=%s",
        run_date.isoformat(),
        dry_run,
        len(tickers),
    )

    for ticker in tickers:
        try:
            quote = fmp.get_quote(ticker)
            ohlc = yfinance.get_ohlc_2y(ticker)
            ma_50_day = _compute_ma_50(ohlc, quote.price)
            high_52_week = (
                quote.year_high_52w
                if quote.year_high_52w and quote.year_high_52w > 0
                else _compute_high_52w(ohlc, quote.price)
            )
            stock_return_1m = _compute_one_month_return(ohlc)

            peg_ratio: float | None = None
            fcf_series: Sequence[float | None] | None = None

            try:
                fundamentals = fmp.get_fundamentals(ticker)
                cash_flows = fmp.get_cash_flow_statement_quarter(ticker)
                peg_ratio = fundamentals.peg_ratio
                fcf_series = _to_chronological_fcf_series(cash_flows)

                if not dry_run:
                    repo.fundamentals_cache_upsert(
                        ticker=ticker,
                        as_of_date=run_date.isoformat(),
                        peg_ratio=peg_ratio,
                        fcf_yield=fundamentals.free_cash_flow,
                        raw_payload={
                            "ticker": fundamentals.ticker,
                            "peg_ratio": fundamentals.peg_ratio,
                            "free_cash_flow": fundamentals.free_cash_flow,
                            "fcf_report_date": (
                                fundamentals.fcf_report_date.isoformat()
                                if fundamentals.fcf_report_date
                                else None
                            ),
                        },
                    )
            except FMPRateLimitError:
                cached = repo.fundamentals_cache_query(ticker)
                peg_ratio = cached.get("peg_ratio") if cached else None
                cached_fcf = cached.get("fcf_yield") if cached else None
                fcf_series = [cached_fcf, cached_fcf, cached_fcf] if cached_fcf is not None else None
                log_warning(
                    "pipeline_fundamentals_fallback",
                    extra={"ticker": ticker, "source": "supabase_cache", "reason": "rate_limit"},
                )
            except FMPClientError:
                log_warning(
                    "pipeline_fundamentals_missing",
                    extra={"ticker": ticker, "source": "fmp"},
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

            if dry_run:
                dry_run_skipped_writes += 1
            else:
                repo.snapshot_upsert(
                    ticker=ticker,
                    snapshot_date=run_date.isoformat(),
                    price_gap=conviction.price_gap_percent,
                    conviction_score=conviction.conviction_score,
                    is_recovery=conviction.is_recovery,
                )
                persisted += 1

            processed += 1
            LOGGER.info(
                "pipeline_ticker_processed ticker=%s date=%s conviction_score=%s price_gap=%s persisted=%s",
                ticker,
                run_date.isoformat(),
                conviction.conviction_score,
                conviction.price_gap_percent,
                not dry_run,
            )
        except (FMPClientError, YFinanceClientError, ValueError) as exc:
            errors += 1
            log_error("pipeline_ticker_error", exc=exc, extra={"ticker": ticker})

    summary = PipelineSummary(
        run_date=run_date.isoformat(),
        total_tickers=len(tickers),
        processed=processed,
        persisted=persisted,
        dry_run_skipped_writes=dry_run_skipped_writes,
        errors=errors,
        read_only_mode=fmp.read_only,
    )
    LOGGER.info("pipeline_complete %s", json.dumps(asdict(summary), sort_keys=True))
    return summary


def _load_fmp_api_key() -> str:
    api_key = os.environ.get("FMP_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing required FMP_API_KEY for pipeline execution.")
    return api_key


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


def _safe_benchmark_return(yfinance_client: YFinanceClient) -> float | None:
    try:
        spy_bars = yfinance_client.get_ohlc_2y("SPY")
        return _compute_one_month_return(spy_bars)
    except YFinanceClientError as exc:
        LOGGER.warning("pipeline_benchmark_unavailable ticker=SPY error=%s", exc)
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


def _parse_date(date_value: str | None) -> date | None:
    if not date_value:
        return None
    return datetime.strptime(date_value, "%Y-%m-%d").date()


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AlphaDip daily snapshot pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute pipeline outputs without writing to DB",
    )
    parser.add_argument("--date", help="Run date in YYYY-MM-DD format (defaults to today)")
    return parser


def run_from_cli(argv: Sequence[str]) -> PipelineSummary:
    parser = _build_cli_parser()
    args = parser.parse_args(list(argv))
    return run_daily_snapshot_pipeline(as_of_date=_parse_date(args.date), dry_run=args.dry_run)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cli_summary = run_from_cli(os.sys.argv[1:])
    print(json.dumps(asdict(cli_summary), sort_keys=True))
