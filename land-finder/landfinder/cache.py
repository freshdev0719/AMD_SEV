"""요청 결과를 SQLite에 잠시 저장해 네이버에 같은 요청을 반복하지 않게 한다."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional


class Cache:
    def __init__(self, path: str, clock: Callable[[], float] = time.time):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, saved_at REAL NOT NULL, value TEXT NOT NULL)"
        )
        self._lock = threading.Lock()
        self._clock = clock

    def get(self, key: str, ttl_seconds: float) -> Optional[Any]:
        with self._lock:
            row = self._conn.execute("SELECT saved_at, value FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or self._clock() - row[0] > ttl_seconds:
            return None
        return json.loads(row[1])

    def set(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, saved_at, value) VALUES (?, ?, ?)",
                (key, self._clock(), json.dumps(value, ensure_ascii=False)),
            )

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM cache")
