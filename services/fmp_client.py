from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Dict, List

import requests

from .cache import AlphaDipCachePolicy


class FMPClientError(RuntimeError):
    pass


class FMPRateLimitError(FMPClientError):
    pass


@dataclass(frozen=True)
class QuoteData:
    ticker: str
    price: float
    change_percent: float | None
    year_high_52w: float | None
    fetched_at: datetime


@dataclass(frozen=True)
class FundamentalsData:
    ticker: str
    peg_ratio: float | None
    free_cash_flow: float | None
    fcf_report_date: date | None
    fetched_at: datetime


class FMPClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://financialmodelingprep.com",
        session: Any = requests,
        timeout_seconds: int = 15,
        cache_policy: AlphaDipCachePolicy | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout_seconds = timeout_seconds
        self.cache_policy = cache_policy
        self.logger = logger or logging.getLogger(__name__)
        self.read_only = False

    def get_quote(self, ticker: str, *, use_cache: bool = True) -> QuoteData:
        normalized = _normalize_ticker(ticker)
        if use_cache and self.cache_policy is not None:
            cached = self.cache_policy.get_quote(normalized)
            if cached is not None and isinstance(cached, QuoteData):
                return cached

        rows = self._request_json(f"/api/v3/quote/{normalized}")
        if not rows:
            raise FMPClientError(f"No quote data returned for ticker {normalized}.")

        row = rows[0]
        quote = QuoteData(
            ticker=normalized,
            price=_to_float(row.get("price"), default=0.0),
            change_percent=_to_optional_float(row.get("changesPercentage")),
            year_high_52w=_to_optional_float(row.get("yearHigh")),
            fetched_at=datetime.now(timezone.utc),
        )

        if self.cache_policy is not None:
            self.cache_policy.set_quote(normalized, quote)

        return quote

    def get_ratios_ttm(self, ticker: str) -> Dict[str, float | None]:
        normalized = _normalize_ticker(ticker)
        rows = self._request_json(f"/api/v3/ratios-ttm/{normalized}")
        row = rows[0] if rows else {}
        peg_raw = row.get("pegRatioTTM", row.get("pegRatio"))
        return {"ticker": normalized, "peg_ratio": _to_optional_float(peg_raw)}

    def get_cash_flow_statement_quarter(self, ticker: str, *, limit: int = 4) -> List[Dict[str, Any]]:
        normalized = _normalize_ticker(ticker)
        rows = self._request_json(
            f"/api/v3/cash-flow-statement/{normalized}",
            params={"period": "quarter", "limit": str(limit)},
        )

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows:
            report_date = _to_optional_date(row.get("date"))
            normalized_rows.append(
                {
                    "ticker": normalized,
                    "report_date": report_date,
                    "free_cash_flow": _to_optional_float(row.get("freeCashFlow")),
                }
            )
        return normalized_rows

    def get_fundamentals(self, ticker: str, *, as_of: date | None = None, use_cache: bool = True) -> FundamentalsData:
        normalized = _normalize_ticker(ticker)
        as_of_date = as_of or datetime.now(timezone.utc).date()

        if use_cache and self.cache_policy is not None:
            cached = self.cache_policy.get_fundamentals(normalized, as_of_date)
            if cached is not None and isinstance(cached, FundamentalsData):
                return cached

        ratios = self.get_ratios_ttm(normalized)
        cash_flows = self.get_cash_flow_statement_quarter(normalized)
        latest_fcf = next((row for row in cash_flows if row.get("free_cash_flow") is not None), None)

        fundamentals = FundamentalsData(
            ticker=normalized,
            peg_ratio=ratios.get("peg_ratio"),
            free_cash_flow=latest_fcf.get("free_cash_flow") if latest_fcf else None,
            fcf_report_date=latest_fcf.get("report_date") if latest_fcf else None,
            fetched_at=datetime.now(timezone.utc),
        )

        if self.cache_policy is not None:
            self.cache_policy.set_fundamentals(normalized, as_of_date, fundamentals)

        return fundamentals

    def _request_json(self, path: str, params: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
        if self.read_only:
            raise FMPRateLimitError("FMP client is in read-only mode after previous HTTP 429.")

        request_params = dict(params or {})
        request_params["apikey"] = self.api_key
        url = f"{self.base_url}{path}"

        start = perf_counter()
        try:
            response = self.session.get(url, params=request_params, timeout=self.timeout_seconds)
            latency_ms = int((perf_counter() - start) * 1000)
            self.logger.info("fmp_request_success path=%s status=%s latency_ms=%s", path, response.status_code, latency_ms)

            if response.status_code == 429:
                self.read_only = True
                self.logger.error("fmp_rate_limited path=%s latency_ms=%s switched_read_only=true", path, latency_ms)
                raise FMPRateLimitError("FMP API rate limit reached (HTTP 429).")

            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return [payload]
            raise FMPClientError("Unexpected FMP response format.")
        except FMPRateLimitError:
            raise
        except requests.RequestException as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            self.logger.error("fmp_request_error path=%s latency_ms=%s error=%s", path, latency_ms, exc)
            raise FMPClientError(f"FMP request failed for {path}.") from exc


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise FMPClientError("Ticker cannot be empty.")
    return normalized


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any, *, default: float) -> float:
    parsed = _to_optional_float(value)
    return parsed if parsed is not None else default


def _to_optional_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None
