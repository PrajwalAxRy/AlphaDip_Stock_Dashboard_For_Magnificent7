from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import List

import yfinance as yf


class YFinanceClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class OhlcBar:
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class YFinanceClient:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    def get_ohlc_2y(self, ticker: str) -> List[OhlcBar]:
        normalized = _normalize_ticker(ticker)
        start = perf_counter()

        try:
            history = yf.Ticker(normalized).history(period="2y", interval="1d", auto_adjust=False)
            latency_ms = int((perf_counter() - start) * 1000)
            self.logger.info("yfinance_history_success ticker=%s rows=%s latency_ms=%s", normalized, len(history), latency_ms)
        except Exception as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            self.logger.error("yfinance_history_error ticker=%s latency_ms=%s error=%s", normalized, latency_ms, exc)
            raise YFinanceClientError(f"Failed to fetch yfinance OHLC for {normalized}.") from exc

        if history is None or history.empty:
            return []

        bars: List[OhlcBar] = []
        for idx, row in history.iterrows():
            bar_date = idx.date() if hasattr(idx, "date") else idx

            # Defensive: skip rows with NaN or missing critical fields
            open_val = _safe_float(row.get("Open"), 0.0)
            high_val = _safe_float(row.get("High"), 0.0)
            low_val = _safe_float(row.get("Low"), 0.0)
            close_val = _safe_float(row.get("Close"), 0.0)
            volume_val = _safe_int(row.get("Volume"), 0)

            if close_val <= 0:
                continue  # skip invalid bars

            bars.append(
                OhlcBar(
                    ticker=normalized,
                    date=bar_date,
                    open=open_val,
                    high=high_val,
                    low=low_val,
                    close=close_val,
                    volume=volume_val,
                )
            )

        return bars


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise YFinanceClientError("Ticker cannot be empty.")
    return normalized


def _safe_float(value: object, default: float) -> float:
    """Convert *value* to float, returning *default* for None / NaN / invalid."""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int) -> int:
    """Convert *value* to int, returning *default* for None / NaN / invalid."""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default
