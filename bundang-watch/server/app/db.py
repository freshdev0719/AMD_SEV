from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .config import KST
from .molit import Trade
from .ranking import TradeRow

SCHEMA = """
CREATE TABLE IF NOT EXISTS complexes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    dong        TEXT NOT NULL,
    jibun       TEXT,
    build_year  INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    complex_id   TEXT NOT NULL REFERENCES complexes(id),
    deal_date    TEXT NOT NULL,
    area         REAL NOT NULL,
    floor        INTEGER,
    price        INTEGER NOT NULL,
    deal_type    TEXT,
    cancelled    INTEGER NOT NULL DEFAULT 0,
    collected_at TEXT NOT NULL,
    UNIQUE (complex_id, deal_date, area, floor, price)
);

CREATE INDEX IF NOT EXISTS idx_trades_complex_date ON trades (complex_id, deal_date);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades (deal_date);

CREATE TABLE IF NOT EXISTS collect_log (
    year_month TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    trade_count INTEGER NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_trades(conn: sqlite3.Connection, trades: list[Trade]) -> None:
    now = datetime.now(KST).isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            """
            INSERT INTO complexes (id, name, dong, jibun, build_year)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                dong = excluded.dong,
                jibun = COALESCE(excluded.jibun, complexes.jibun),
                build_year = COALESCE(excluded.build_year, complexes.build_year)
            """,
            {(t.complex_id, t.apt_name, t.dong, t.jibun, t.build_year) for t in trades},
        )
        # 계약 해제(cdealType)는 나중에 반영되므로 기존 행의 상태를 갱신한다.
        conn.executemany(
            """
            INSERT INTO trades (complex_id, deal_date, area, floor, price, deal_type, cancelled, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (complex_id, deal_date, area, floor, price) DO UPDATE SET
                deal_type = excluded.deal_type,
                cancelled = excluded.cancelled
            """,
            [
                (t.complex_id, t.deal_date.isoformat(), t.area, t.floor, t.price, t.deal_type, int(t.cancelled), now)
                for t in trades
            ],
        )


def log_collect(conn: sqlite3.Connection, year_month: str, count: int) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO collect_log (year_month, fetched_at, trade_count) VALUES (?, ?, ?)
            ON CONFLICT (year_month) DO UPDATE SET
                fetched_at = excluded.fetched_at, trade_count = excluded.trade_count
            """,
            (year_month, datetime.now(KST).isoformat(timespec="seconds"), count),
        )


def last_collected_at(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(fetched_at) FROM collect_log").fetchone()[0]


def load_trades(conn: sqlite3.Connection, complex_id: str | None = None) -> list[TradeRow]:
    sql = "SELECT id, complex_id, deal_date, area, floor, price, deal_type, cancelled FROM trades"
    params: tuple = ()
    if complex_id is not None:
        sql += " WHERE complex_id = ?"
        params = (complex_id,)
    return [
        TradeRow(
            id=r["id"],
            complex_id=r["complex_id"],
            deal_date=date.fromisoformat(r["deal_date"]),
            area=r["area"],
            floor=r["floor"],
            price=r["price"],
            deal_type=r["deal_type"],
            cancelled=bool(r["cancelled"]),
        )
        for r in conn.execute(sql, params)
    ]


def load_complexes(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["id"]: r for r in conn.execute("SELECT * FROM complexes")}


def get_complex(conn: sqlite3.Connection, complex_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM complexes WHERE id = ?", (complex_id,)).fetchone()
