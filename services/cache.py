from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Generic, TypeVar

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    value: T
    expires_at: datetime
    quarter: str | None = None


class TTLCache(Generic[T]):
    def __init__(self, now_fn: Callable[[], datetime] = _utc_now) -> None:
        self._store: Dict[str, CacheEntry[T]] = {}
        self._now_fn = now_fn

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None

        if entry.expires_at <= self._now_fn():
            self._store.pop(key, None)
            return None

        return entry.value

    def get_entry(self, key: str) -> CacheEntry[T] | None:
        entry = self._store.get(key)
        if entry is None:
            return None

        if entry.expires_at <= self._now_fn():
            self._store.pop(key, None)
            return None

        return entry

    def set(self, key: str, value: T, ttl_seconds: int, quarter: str | None = None) -> T:
        expires_at = self._now_fn().replace(microsecond=0) + timedelta(seconds=max(ttl_seconds, 0))
        self._store[key] = CacheEntry(value=value, expires_at=expires_at, quarter=quarter)
        return value


@dataclass
class AlphaDipCachePolicy:
    quote_ttl_seconds: int = 60
    fundamentals_ttl_seconds: int = 60 * 60 * 24 * 95
    now_fn: Callable[[], datetime] = _utc_now

    def __post_init__(self) -> None:
        self.quote_cache: TTLCache[object] = TTLCache(now_fn=self.now_fn)
        self.fundamentals_cache: TTLCache[object] = TTLCache(now_fn=self.now_fn)

    def get_quote(self, ticker: str) -> object | None:
        return self.quote_cache.get(_cache_key(ticker))

    def set_quote(self, ticker: str, value: object) -> object:
        return self.quote_cache.set(_cache_key(ticker), value, ttl_seconds=self.quote_ttl_seconds)

    def get_fundamentals(self, ticker: str, as_of: date) -> object | None:
        entry = self.fundamentals_cache.get_entry(_cache_key(ticker))
        if entry is None:
            return None

        requested_quarter = quarter_key(as_of)
        if entry.quarter is not None and entry.quarter != requested_quarter:
            return None

        return entry.value

    def set_fundamentals(self, ticker: str, as_of: date, value: object) -> object:
        return self.fundamentals_cache.set(
            _cache_key(ticker),
            value,
            ttl_seconds=self.fundamentals_ttl_seconds,
            quarter=quarter_key(as_of),
        )


def _cache_key(ticker: str) -> str:
    return ticker.strip().upper()


def quarter_key(as_of: date) -> str:
    quarter = ((as_of.month - 1) // 3) + 1
    return f"{as_of.year}-Q{quarter}"
