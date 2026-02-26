from __future__ import annotations

import logging
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

        if history.empty:
            return []

        bars: List[OhlcBar] = []
        for idx, row in history.iterrows():
            bar_date = idx.date() if hasattr(idx, "date") else idx
            bars.append(
                OhlcBar(
                    ticker=normalized,
                    date=bar_date,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )

        return bars


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise YFinanceClientError("Ticker cannot be empty.")
    return normalized
