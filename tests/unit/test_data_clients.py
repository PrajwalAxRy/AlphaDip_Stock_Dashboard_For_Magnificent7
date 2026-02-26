from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import pytest
import requests

from services.cache import AlphaDipCachePolicy
from services.fmp_client import (
    FMPAuthenticationError,
    FMPClient,
    FMPConnectivityError,
    FMPRateLimitError,
    FMPSubscriptionError,
)
from services.yfinance_client import YFinanceClient

pytestmark = pytest.mark.unit


@dataclass
class FakeResponse:
    status_code: int
    payload: Any
    error: Exception | None = None

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self.responses:
            raise AssertionError("No fake responses left")
        return self.responses.pop(0)


def test_fmp_quote_uses_cache_hit_after_miss() -> None:
    session = FakeSession(
        responses=[
            FakeResponse(
                status_code=200,
                payload=[{"symbol": "MSFT", "price": 400.25, "changesPercentage": 1.2, "yearHigh": 468.0}],
            )
        ]
    )
    cache = AlphaDipCachePolicy(quote_ttl_seconds=60)
    client = FMPClient(api_key="test-key", session=session, cache_policy=cache)

    first = client.get_quote("msft")
    second = client.get_quote("MSFT")

    assert first == second
    assert first.ticker == "MSFT"
    assert first.price == 400.25
    assert len(session.calls) == 1


def test_null_peg_response_is_handled_without_exception() -> None:
    session = FakeSession(
        responses=[
            FakeResponse(status_code=200, payload=[{"pegRatioTTM": None}]),
            FakeResponse(
                status_code=200,
                payload=[{"date": "2026-02-01", "freeCashFlow": 12000000000}],
            ),
        ]
    )
    client = FMPClient(api_key="test-key", session=session)

    fundamentals = client.get_fundamentals("NVDA", as_of=date(2026, 2, 26), use_cache=False)

    assert fundamentals.ticker == "NVDA"
    assert fundamentals.peg_ratio is None
    assert fundamentals.free_cash_flow == 12000000000.0


def test_http_429_switches_client_to_read_only_mode() -> None:
    session = FakeSession(responses=[FakeResponse(status_code=429, payload=[])] )
    client = FMPClient(api_key="test-key", session=session)

    with pytest.raises(FMPRateLimitError):
        client.get_quote("TSLA", use_cache=False)

    assert client.read_only is True

    with pytest.raises(FMPRateLimitError):
        client.get_quote("TSLA", use_cache=False)

    assert len(session.calls) == 1


def test_http_401_is_classified_as_authentication_error() -> None:
    session = FakeSession(responses=[FakeResponse(status_code=401, payload={"Error Message": "Invalid API KEY."})])
    client = FMPClient(api_key="test-key", session=session)

    with pytest.raises(FMPAuthenticationError):
        client.get_quote("TSLA", use_cache=False)


def test_request_exception_is_classified_as_connectivity_error() -> None:
    error = requests.Timeout("request timed out")
    session = FakeSession(
        responses=[
            FakeResponse(
                status_code=200,
                payload=[],
                error=error,
            )
        ]
    )
    client = FMPClient(api_key="test-key", session=session)

    with pytest.raises(FMPConnectivityError):
        client.get_quote("TSLA", use_cache=False)


def test_quote_uses_stable_endpoint_and_symbol_param() -> None:
    session = FakeSession(
        responses=[
            FakeResponse(
                status_code=200,
                payload=[{"symbol": "MSFT", "price": 400.25, "changesPercentage": 1.2, "yearHigh": 468.0}],
            )
        ]
    )
    client = FMPClient(api_key="test-key", session=session)

    client.get_quote("MSFT", use_cache=False)

    assert session.calls[0]["url"].endswith("/stable/quote")
    assert session.calls[0]["params"]["symbol"] == "MSFT"


def test_legacy_endpoint_message_is_classified_as_subscription_error() -> None:
    session = FakeSession(
        responses=[
            FakeResponse(
                status_code=200,
                payload={
                    "Error Message": (
                        "Legacy Endpoint : Due to Legacy endpoints being no longer supported"
                    )
                },
            )
        ]
    )
    client = FMPClient(api_key="test-key", session=session)

    with pytest.raises(FMPSubscriptionError):
        client.get_quote("AAPL", use_cache=False)


def test_yfinance_ohlc_normalization_with_mocked_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.5],
            "Close": [101.5, 102.5],
            "Volume": [1000000, 1200000],
        },
        index=pd.to_datetime(["2026-02-24", "2026-02-25"]),
    )

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, period: str, interval: str, auto_adjust: bool) -> pd.DataFrame:
            assert self.symbol == "AMZN"
            assert period == "2y"
            assert interval == "1d"
            assert auto_adjust is False
            return frame

    monkeypatch.setattr("services.yfinance_client.yf.Ticker", FakeTicker)

    client = YFinanceClient()
    bars = client.get_ohlc_2y("amzn")

    assert len(bars) == 2
    assert bars[0].ticker == "AMZN"
    assert bars[0].open == 100.0
    assert bars[1].close == 102.5
