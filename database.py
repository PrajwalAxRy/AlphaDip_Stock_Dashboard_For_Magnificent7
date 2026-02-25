from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List

if TYPE_CHECKING:
    from supabase import Client
else:
    Client = Any


@dataclass(frozen=True)
class DatabaseConfig:
    supabase_url: str | None
    supabase_key: str | None


def load_database_config(config: Dict[str, str] | None = None) -> tuple[DatabaseConfig, List[str]]:
    source = config or os.environ
    db_config = DatabaseConfig(
        supabase_url=source.get("SUPABASE_URL"),
        supabase_key=source.get("SUPABASE_KEY"),
    )

    missing = []
    if not db_config.supabase_url:
        missing.append("SUPABASE_URL")
    if not db_config.supabase_key:
        missing.append("SUPABASE_KEY")

    return db_config, missing


class DatabaseError(RuntimeError):
    pass


class DatabaseConfigurationError(DatabaseError):
    pass


class DatabaseConnectionError(DatabaseError):
    pass


class DatabaseOperationError(DatabaseError):
    pass


def create_supabase_client(
    config: Dict[str, str] | None = None,
    client_factory: Callable[[str, str], Client] | None = None,
) -> Any:
    db_config, missing = load_database_config(config)
    if missing:
        raise DatabaseConfigurationError(
            "Missing required database configuration: " + ", ".join(missing)
        )

    assert db_config.supabase_url is not None
    assert db_config.supabase_key is not None
    resolved_client_factory = client_factory or _default_client_factory

    try:
        return resolved_client_factory(db_config.supabase_url, db_config.supabase_key)
    except Exception as exc:
        raise DatabaseConnectionError("Unable to connect to Supabase.") from exc


class SupabaseRepository:
    def __init__(self, client: Any) -> None:
        self.client = client

    @classmethod
    def from_config(
        cls,
        config: Dict[str, str] | None = None,
        client_factory: Callable[[str, str], Client] | None = None,
    ) -> "SupabaseRepository":
        return cls(create_supabase_client(config=config, client_factory=client_factory))

    def watchlist_add(self, ticker: str) -> Dict[str, Any]:
        normalized_ticker = _normalize_ticker(ticker)
        payload = {"ticker": normalized_ticker}
        return self._execute_single(
            lambda: self.client.table("watchlists").upsert(payload, on_conflict="ticker").execute(),
            "Failed to add ticker to watchlist.",
        )

    def watchlist_remove(self, ticker: str) -> int:
        normalized_ticker = _normalize_ticker(ticker)
        response_data = self._execute_data(
            lambda: self.client.table("watchlists").delete().eq("ticker", normalized_ticker).execute(),
            "Failed to remove ticker from watchlist.",
        )
        return len(response_data)

    def watchlist_list(self) -> List[Dict[str, Any]]:
        return self._execute_data(
            lambda: self.client.table("watchlists").select("*").order("ticker").execute(),
            "Failed to list watchlist tickers.",
        )

    def snapshot_upsert(
        self,
        ticker: str,
        snapshot_date: str,
        price_gap: float,
        conviction_score: int,
        is_recovery: bool,
    ) -> Dict[str, Any]:
        payload = {
            "ticker": _normalize_ticker(ticker),
            "date": snapshot_date,
            "price_gap": price_gap,
            "conviction_score": conviction_score,
            "is_recovery": is_recovery,
        }
        return self._execute_single(
            lambda: self.client.table("daily_snapshots")
            .upsert(payload, on_conflict="ticker,date")
            .execute(),
            "Failed to upsert daily snapshot.",
        )

    def snapshot_query(self, ticker: str, limit: int = 90) -> List[Dict[str, Any]]:
        normalized_ticker = _normalize_ticker(ticker)
        return self._execute_data(
            lambda: self.client.table("daily_snapshots")
            .select("*")
            .eq("ticker", normalized_ticker)
            .order("date", desc=True)
            .limit(limit)
            .execute(),
            "Failed to query daily snapshots.",
        )

    def fundamentals_cache_upsert(
        self,
        ticker: str,
        as_of_date: str,
        peg_ratio: float | None,
        fcf_yield: float | None,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "ticker": _normalize_ticker(ticker),
            "as_of_date": as_of_date,
            "peg_ratio": peg_ratio,
            "fcf_yield": fcf_yield,
            "raw_payload": raw_payload,
        }
        return self._execute_single(
            lambda: self.client.table("fundamentals_cache")
            .upsert(payload, on_conflict="ticker")
            .execute(),
            "Failed to upsert fundamentals cache.",
        )

    def fundamentals_cache_query(self, ticker: str) -> Dict[str, Any] | None:
        normalized_ticker = _normalize_ticker(ticker)
        rows = self._execute_data(
            lambda: self.client.table("fundamentals_cache")
            .select("*")
            .eq("ticker", normalized_ticker)
            .limit(1)
            .execute(),
            "Failed to query fundamentals cache.",
        )
        return rows[0] if rows else None

    def _execute_data(self, operation: Callable[[], Any], error_message: str) -> List[Dict[str, Any]]:
        try:
            response = operation()
            return list(getattr(response, "data", []) or [])
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseOperationError(error_message) from exc

    def _execute_single(self, operation: Callable[[], Any], error_message: str) -> Dict[str, Any]:
        rows = self._execute_data(operation, error_message)
        return rows[0] if rows else {}


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise DatabaseOperationError("Ticker cannot be empty.")
    return normalized


def _default_client_factory(url: str, key: str) -> Any:
    try:
        from supabase import create_client
    except ModuleNotFoundError as exc:
        raise DatabaseConnectionError("Supabase client library is not installed.") from exc
    return create_client(url, key)
