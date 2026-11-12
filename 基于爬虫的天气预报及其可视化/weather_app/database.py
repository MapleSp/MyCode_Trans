"""SQLite 持久化层。"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CHINA_TIMEZONE = timezone(timedelta(hours=8))


class WeatherDatabase:
    """保存天气快照与查询记录，不依赖第三方 ORM。"""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=8)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def _connection(self):
        """显式提交并关闭连接，避免 Windows 下文件句柄被长期占用。"""

        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._init_lock:
            with self._connection() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS weather_snapshots (
                        city_code TEXT PRIMARY KEY,
                        city_name TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        fetched_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'weather.com.cn'
                    );
                    CREATE INDEX IF NOT EXISTS idx_weather_expires
                        ON weather_snapshots(expires_at);

                    CREATE TABLE IF NOT EXISTS search_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query TEXT NOT NULL,
                        city_name TEXT,
                        city_code TEXT,
                        client_key TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_search_created
                        ON search_history(created_at DESC);
                    """
                )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(CHINA_TIMEZONE)

    def save_snapshot(
        self,
        city_name: str,
        city_code: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
        source: str,
    ) -> None:
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO weather_snapshots
                    (city_code, city_name, payload, fetched_at, expires_at, source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(city_code) DO UPDATE SET
                    city_name = excluded.city_name,
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at,
                    source = excluded.source
                """,
                (
                    city_code,
                    city_name,
                    serialized,
                    now.isoformat(),
                    expires_at.isoformat(),
                    source,
                ),
            )

    def get_snapshot(self, city_code: str, max_age_hours: int = 168) -> dict[str, Any] | None:
        threshold = (self._now() - timedelta(hours=max_age_hours)).isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload, fetched_at, expires_at, source
                FROM weather_snapshots
                WHERE city_code = ? AND fetched_at >= ?
                """,
                (city_code, threshold),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            return None
        payload["_snapshot"] = {
            "fetched_at": row["fetched_at"],
            "expires_at": row["expires_at"],
            "source": row["source"],
            "fresh": row["expires_at"] > self._now().isoformat(),
        }
        return payload

    def add_search(
        self,
        query: str,
        city_name: str | None,
        city_code: str | None,
        client_key: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO search_history(query, city_name, city_code, client_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    query[:80],
                    city_name,
                    city_code,
                    client_key[:100],
                    self._now().isoformat(),
                ),
            )

    def recent_searches(self, client_key: str, limit: int = 6) -> list[dict[str, str | None]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT query, city_name, city_code, MAX(created_at) AS created_at
                FROM search_history
                WHERE client_key = ? AND city_name IS NOT NULL
                GROUP BY city_name
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (client_key[:100], limit),
            ).fetchall()
        return [
            {
                "query": row["query"],
                "name": row["city_name"],
                "code": row["city_code"],
            }
            for row in rows
        ]

    def purge_expired(self, keep_hours: int = 720) -> int:
        threshold = (self._now() - timedelta(hours=keep_hours)).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM weather_snapshots WHERE fetched_at < ?",
                (threshold,),
            )
            return cursor.rowcount

    def health(self) -> bool:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
