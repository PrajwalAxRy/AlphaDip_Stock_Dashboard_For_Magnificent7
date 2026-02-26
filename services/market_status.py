"""Market status utility — weekend/holiday detection and last-trading-date logic.

Used by the UI and pipeline to decide whether to fetch live quotes or fall back
to the most recent valid snapshot stored in Supabase.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

# US Eastern offset (UTC-5 / UTC-4 DST).  We keep it simple and use a fixed
# offset for the closing-time heuristic rather than pulling in ``pytz``.
_ET_OFFSET = timezone(timedelta(hours=-5))

# NYSE regular session: 9:30 AM – 4:00 PM ET
_MARKET_OPEN_TIME = time(9, 30)
_MARKET_CLOSE_TIME = time(16, 0)

# Well-known US market holidays (month, day) — static set covering the most
# common fixed-date closures.  Floating holidays (Thanksgiving, etc.) are
# approximated; a production system would use a calendar service.
_STATIC_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),   # New Year's Day
        (1, 20),  # MLK Day (approx)
        (2, 17),  # Presidents' Day (approx)
        (7, 4),   # Independence Day
        (9, 1),   # Labor Day (approx)
        (12, 25), # Christmas Day
    }
)


def _to_et(dt: datetime) -> datetime:
    """Convert a timezone-aware *datetime* to US-Eastern."""
    return dt.astimezone(_ET_OFFSET)


def is_weekend(d: date | None = None) -> bool:
    """Return ``True`` when *d* falls on a Saturday or Sunday."""
    target = d or datetime.now(timezone.utc).date()
    return target.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def is_known_holiday(d: date | None = None) -> bool:
    """Return ``True`` when *d* matches a well-known US market holiday."""
    target = d or datetime.now(timezone.utc).date()
    return (target.month, target.day) in _STATIC_HOLIDAYS


def is_market_closed(d: date | None = None) -> bool:
    """Return ``True`` when the market is closed for the entire day."""
    target = d or datetime.now(timezone.utc).date()
    return is_weekend(target) or is_known_holiday(target)


def is_market_open_now(now: datetime | None = None) -> bool:
    """Return ``True`` when the US stock market is currently in session.

    Checks both the date (weekend / holiday) and the intra-day window.
    """
    utc_now = now or datetime.now(timezone.utc)
    et_now = _to_et(utc_now)
    if is_market_closed(et_now.date()):
        return False
    return _MARKET_OPEN_TIME <= et_now.time() <= _MARKET_CLOSE_TIME


def last_trading_date(as_of: date | None = None) -> date:
    """Return the most recent date on which the market was open.

    If *as_of* itself is a trading day the function returns *as_of*.
    """
    target = as_of or datetime.now(timezone.utc).date()
    # Walk backwards at most 10 days to skip extended weekends / holidays.
    for _ in range(10):
        if not is_market_closed(target):
            return target
        target -= timedelta(days=1)
    return target  # defensive fallback


def should_skip_live_fetch(now: datetime | None = None) -> bool:
    """Return ``True`` when the app should *not* issue live quote requests.

    On weekends and holidays the latest persisted snapshot should be served
    instead of attempting (and wasting) a live API call.
    """
    utc_now = now or datetime.now(timezone.utc)
    et_now = _to_et(utc_now)
    return is_market_closed(et_now.date())
