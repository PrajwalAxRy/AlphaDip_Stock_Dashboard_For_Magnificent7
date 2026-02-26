from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from services.cache import AlphaDipCachePolicy


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current


def test_quote_cache_hit_and_expiry_behavior() -> None:
    clock = MutableClock(datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc))
    cache = AlphaDipCachePolicy(quote_ttl_seconds=30, now_fn=clock.now)

    assert cache.get_quote("MSFT") is None

    cache.set_quote("MSFT", {"price": 410.5})
    assert cache.get_quote("MSFT") == {"price": 410.5}

    clock.current += timedelta(seconds=31)
    assert cache.get_quote("MSFT") is None


def test_fundamentals_cache_reuses_same_quarter_only() -> None:
    clock = MutableClock(datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc))
    cache = AlphaDipCachePolicy(now_fn=clock.now)

    payload = {"peg_ratio": 1.1}
    cache.set_fundamentals("AAPL", date(2026, 2, 15), payload)

    assert cache.get_fundamentals("AAPL", date(2026, 3, 30)) == payload
    assert cache.get_fundamentals("AAPL", date(2026, 4, 1)) is None
