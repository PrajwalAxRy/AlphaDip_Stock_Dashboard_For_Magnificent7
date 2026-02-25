from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class DatabaseConfig:
    supabase_url: str | None
    supabase_key: str | None


def load_database_config(config: Dict[str, str] | None = None) -> tuple[DatabaseConfig, List[str]]:
    source = config or {}
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
