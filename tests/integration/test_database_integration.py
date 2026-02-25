from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pytest

from database import (
    DatabaseConnectionError,
    DatabaseConfigurationError,
    SupabaseRepository,
    create_supabase_client,
)

pytestmark = pytest.mark.integration


@dataclass
class FakeResponse:
    data: List[Dict[str, Any]]


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            "watchlists": [],
            "daily_snapshots": [],
            "fundamentals_cache": [],
        }
        self._snapshot_id = 1

    def table(self, name: str) -> "FakeTableQuery":
        return FakeTableQuery(self, name)


class FakeTableQuery:
    def __init__(self, client: FakeSupabaseClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload: Dict[str, Any] | None = None
        self.filters: Dict[str, Any] = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, _columns: str = "*") -> "FakeTableQuery":
        self.operation = "select"
        return self

    def insert(self, payload: Dict[str, Any]) -> "FakeTableQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def upsert(self, payload: Dict[str, Any], on_conflict: str | None = None) -> "FakeTableQuery":
        self.operation = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def delete(self) -> "FakeTableQuery":
        self.operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters[column] = value
        return self

    def order(self, column: str, desc: bool = False) -> "FakeTableQuery":
        self._order = (column, desc)
        return self

    def limit(self, n: int) -> "FakeTableQuery":
        self._limit = n
        return self

    def execute(self) -> FakeResponse:
        table = self.client.tables[self.table_name]

        if self.operation == "upsert":
            assert self.payload is not None
            if self.table_name == "watchlists":
                existing = next((row for row in table if row["ticker"] == self.payload["ticker"]), None)
                if existing:
                    existing.update(self.payload)
                    return FakeResponse([existing.copy()])
                row = self.payload.copy()
                row.setdefault("added_at", "2026-02-26T00:00:00Z")
                table.append(row)
                return FakeResponse([row.copy()])

            if self.table_name == "daily_snapshots":
                existing = next(
                    (
                        row
                        for row in table
                        if row["ticker"] == self.payload["ticker"] and row["date"] == self.payload["date"]
                    ),
                    None,
                )
                if existing:
                    existing.update(self.payload)
                    return FakeResponse([existing.copy()])
                row = self.payload.copy()
                row["id"] = self.client._snapshot_id
                self.client._snapshot_id += 1
                table.append(row)
                return FakeResponse([row.copy()])

            if self.table_name == "fundamentals_cache":
                existing = next((row for row in table if row["ticker"] == self.payload["ticker"]), None)
                if existing:
                    existing.update(self.payload)
                    return FakeResponse([existing.copy()])
                row = self.payload.copy()
                table.append(row)
                return FakeResponse([row.copy()])

        if self.operation == "delete":
            remaining = []
            removed = []
            for row in table:
                if all(row.get(k) == v for k, v in self.filters.items()):
                    removed.append(row)
                else:
                    remaining.append(row)
            self.client.tables[self.table_name] = remaining
            return FakeResponse([row.copy() for row in removed])

        if self.operation == "select":
            rows = [row.copy() for row in table if all(row.get(k) == v for k, v in self.filters.items())]
            if self._order is not None:
                key, desc = self._order
                rows = sorted(rows, key=lambda r: r.get(key), reverse=desc)
            if self._limit is not None:
                rows = rows[: self._limit]
            return FakeResponse(rows)

        if self.operation == "insert":
            assert self.payload is not None
            row = self.payload.copy()
            table.append(row)
            return FakeResponse([row.copy()])

        raise AssertionError(f"Unsupported operation {self.operation}")


def test_migration_sql_contains_required_schema() -> None:
    migration = Path("migrations/001_initial_schema.sql")
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists watchlists" in sql
    assert "create table if not exists daily_snapshots" in sql
    assert "create table if not exists fundamentals_cache" in sql
    assert "unique (ticker, date)" in sql
    assert "ticker text not null unique" in sql


def test_watchlist_snapshot_and_cache_crud() -> None:
    repo = SupabaseRepository(FakeSupabaseClient())

    repo.watchlist_add(" msft ")
    repo.watchlist_add("AAPL")
    listed = repo.watchlist_list()
    assert [row["ticker"] for row in listed] == ["AAPL", "MSFT"]

    first = repo.snapshot_upsert(
        ticker="MSFT",
        snapshot_date="2026-02-25",
        price_gap=22.5,
        conviction_score=68,
        is_recovery=False,
    )
    second = repo.snapshot_upsert(
        ticker="MSFT",
        snapshot_date="2026-02-26",
        price_gap=20.2,
        conviction_score=72,
        is_recovery=True,
    )

    snapshots = repo.snapshot_query("MSFT")
    assert len(snapshots) == 2
    assert snapshots[0]["conviction_score"] == 72
    assert snapshots[0]["is_recovery"] is True
    assert first["id"] != second["id"]

    repo.fundamentals_cache_upsert(
        ticker="MSFT",
        as_of_date="2026-02-25",
        peg_ratio=1.2,
        fcf_yield=0.08,
        raw_payload={"source": "fmp"},
    )
    repo.fundamentals_cache_upsert(
        ticker="MSFT",
        as_of_date="2026-02-26",
        peg_ratio=None,
        fcf_yield=0.09,
        raw_payload={"source": "cache"},
    )

    cached = repo.fundamentals_cache_query("MSFT")
    assert cached is not None
    assert cached["as_of_date"] == "2026-02-26"
    assert cached["raw_payload"]["source"] == "cache"

    removed = repo.watchlist_remove("AAPL")
    assert removed == 1
    assert [row["ticker"] for row in repo.watchlist_list()] == ["MSFT"]


def test_missing_config_raises_controlled_error() -> None:
    with pytest.raises(DatabaseConfigurationError):
        create_supabase_client(config={})


def test_connection_failure_raises_controlled_error() -> None:
    def failing_factory(_url: str, _key: str) -> Any:
        raise RuntimeError("network down")

    with pytest.raises(DatabaseConnectionError):
        create_supabase_client(
            config={"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "key"},
            client_factory=failing_factory,
        )
