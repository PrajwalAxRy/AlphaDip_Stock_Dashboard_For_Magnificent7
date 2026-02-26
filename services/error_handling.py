"""Centralized error-handling utilities — correlation IDs, user-safe messages,
and structured logging helpers.

Every error surfaced to the user goes through ``user_safe_message`` so that
internal details (tracebacks, SQL errors, API keys) are never leaked.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("alphadip.errors")


# ---------------------------------------------------------------------------
# Correlation IDs
# ---------------------------------------------------------------------------

def generate_correlation_id() -> str:
    """Return a short, unique correlation ID suitable for log lines and UI."""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# User-safe error messages
# ---------------------------------------------------------------------------

_USER_MESSAGES: dict[str, str] = {
    "db_connection": "Unable to connect to the database. Please try again later.",
    "db_operation": "A database error occurred. Please try again later.",
    "fmp_rate_limit": "Market data provider is temporarily unavailable (rate limit). Showing cached data.",
    "fmp_error": "Unable to fetch market data. Showing cached data where available.",
    "yfinance_error": "Unable to fetch historical price data. Please try again later.",
    "missing_secrets": "Required configuration is missing. Contact the administrator.",
    "unknown": "An unexpected error occurred. Please try again later.",
    "stale_data": "Displayed data may be stale (last update was more than 24 hours ago).",
    "market_closed": "Market is closed. Showing most recent available data.",
    "read_only_mode": "Running in read-only mode — live market data is unavailable.",
}


def user_safe_message(key: str, **kwargs: Any) -> str:
    """Return a user-facing error string for the given *key*.

    Accepts optional ``correlation_id`` kwarg which is appended to the
    message so users can reference it when reporting issues.
    """
    msg = _USER_MESSAGES.get(key, _USER_MESSAGES["unknown"])
    correlation_id = kwargs.get("correlation_id")
    if correlation_id:
        msg += f" (ref: {correlation_id})"
    return msg


# ---------------------------------------------------------------------------
# Structured logging helpers
# ---------------------------------------------------------------------------

def log_error(
    message: str,
    *,
    exc: BaseException | None = None,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Log an error with a correlation ID and return the ID.

    If no *correlation_id* is supplied one is generated automatically.
    """
    cid = correlation_id or generate_correlation_id()
    parts = [f"correlation_id={cid}", message]
    if extra:
        parts.extend(f"{k}={v}" for k, v in extra.items())

    LOGGER.error(" ".join(parts), exc_info=exc)
    return cid


def log_warning(
    message: str,
    *,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Log a warning with a correlation ID and return the ID."""
    cid = correlation_id or generate_correlation_id()
    parts = [f"correlation_id={cid}", message]
    if extra:
        parts.extend(f"{k}={v}" for k, v in extra.items())

    LOGGER.warning(" ".join(parts))
    return cid


# ---------------------------------------------------------------------------
# Stale-data detection
# ---------------------------------------------------------------------------

_STALE_THRESHOLD_HOURS = 24


def is_quote_stale(fetched_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Return ``True`` when *fetched_at* is more than 24 hours in the past.

    If *fetched_at* is ``None`` the quote is considered stale.
    Gracefully handles ``date`` objects (treated as midnight UTC of that day).
    """
    if fetched_at is None:
        return True
    utc_now = now or datetime.now(timezone.utc)
    # Convert plain date to datetime at midnight UTC
    if isinstance(fetched_at, datetime):
        ts = fetched_at
    else:
        # fetched_at is a date, not datetime
        from datetime import date as _date_type
        if isinstance(fetched_at, _date_type):
            ts = datetime(fetched_at.year, fetched_at.month, fetched_at.day, tzinfo=timezone.utc)
        else:
            return True
    # Ensure both are timezone-aware for comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    elapsed_hours = (utc_now - ts).total_seconds() / 3600.0
    return elapsed_hours > _STALE_THRESHOLD_HOURS
