"""
SQLite-backed cache with per-type TTL.

Cache keys follow the pattern  <type>:<ticker>[:<period>]
TTLs:
  price      – 15 minutes  (live data, refreshes quickly)
  overview   – 1 hour      (company fundamentals change daily)
  history    – 24 hours    (past OHLCV bars are immutable)
  financials – 7 days      (quarterly / annual filings)
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.environ.get("CACHE_DB_PATH", str(Path(__file__).parent.parent / "data" / "stocks_cache.db"))

TTL: dict[str, timedelta] = {
    "price": timedelta(minutes=15),
    "overview": timedelta(hours=1),
    "history": timedelta(hours=24),
    "financials": timedelta(days=7),
}


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            cache_type TEXT NOT NULL,
            data       TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def get(key: str, cache_type: str) -> dict | None:
    """Return cached data if it exists and has not expired, else None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT data, fetched_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    data_json, fetched_at_str = row
    fetched_at = datetime.fromisoformat(fetched_at_str)
    if datetime.utcnow() - fetched_at > TTL[cache_type]:
        return None  # stale

    return json.loads(data_json)


def put(key: str, cache_type: str, data: dict) -> None:
    """Write (or overwrite) a cache entry."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO cache (key, cache_type, data, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, cache_type, json.dumps(data), datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
