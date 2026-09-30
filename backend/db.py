"""SQLite storage: asteroid history + saved briefings (standard library only)."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "asteroid_radar.db",
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS asteroids (
    id                  TEXT NOT NULL,
    approach_time       TEXT NOT NULL,
    date                TEXT NOT NULL,
    name                TEXT,
    diameter_min_m      REAL,
    diameter_max_m      REAL,
    diameter_avg_m      REAL,
    velocity_kms        REAL,
    miss_distance_km    REAL,
    miss_distance_lunar REAL,
    hazardous           INTEGER,
    sentry              INTEGER,
    magnitude           REAL,
    jpl_url             TEXT,
    fetched_at          TEXT,
    PRIMARY KEY (id, approach_time)
);
CREATE INDEX IF NOT EXISTS idx_asteroids_date ON asteroids(date);

CREATE TABLE IF NOT EXISTS briefings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    source      TEXT NOT NULL,
    model       TEXT,
    text        TEXT NOT NULL
);
"""

COLUMNS = [
    "id",
    "approach_time",
    "date",
    "name",
    "diameter_min_m",
    "diameter_max_m",
    "diameter_avg_m",
    "velocity_kms",
    "miss_distance_km",
    "miss_distance_lunar",
    "hazardous",
    "sentry",
    "magnitude",
    "jpl_url",
]
BOOL_COLUMNS = {"hazardous", "sentry"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- asteroids ----------


def save_asteroids(rows: list[dict]) -> int:
    """Insert or update rows. Re-fetching the same window never creates duplicates."""
    if not rows:
        return 0
    fetched_at = _now()
    placeholders = ", ".join("?" for _ in range(len(COLUMNS) + 1))
    sql = (
        f"INSERT OR REPLACE INTO asteroids ({', '.join(COLUMNS)}, fetched_at) "
        f"VALUES ({placeholders})"
    )
    data = [
        tuple(int(r[c]) if c in BOOL_COLUMNS else r.get(c) for c in COLUMNS)
        + (fetched_at,)
        for r in rows
    ]
    with get_conn() as conn:
        conn.executemany(sql, data)
    return len(data)


def get_asteroids(start: str, end: str) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM asteroids WHERE date BETWEEN ? AND ? ORDER BY approach_time",
            (start, end),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["hazardous"] = bool(r["hazardous"])
        r["sentry"] = bool(r["sentry"])
    return rows


def daily_summary(start: str, end: str) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT date,
                   COUNT(*)                 AS total,
                   SUM(hazardous)           AS hazardous,
                   MIN(miss_distance_lunar) AS closest_lunar,
                   MAX(diameter_avg_m)      AS largest_m,
                   MAX(velocity_kms)        AS fastest_kms
            FROM asteroids
            WHERE date BETWEEN ? AND ?
            GROUP BY date
            ORDER BY date
            """,
            (start, end),
        )
        return [dict(r) for r in cur.fetchall()]


def stats() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)             AS total,
                   COUNT(DISTINCT date) AS days_covered,
                   MIN(date)            AS first_date,
                   MAX(date)            AS last_date
            FROM asteroids
            """
        ).fetchone()
    return dict(row)


# ---------- briefings ----------


def save_briefing(start: str, end: str, source: str, model: str | None, text: str) -> dict:
    created_at = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO briefings (created_at, start_date, end_date, source, model, text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (created_at, start, end, source, model, text),
        )
        new_id = cur.lastrowid
    return {
        "id": new_id,
        "created_at": created_at,
        "start_date": start,
        "end_date": end,
        "source": source,
        "model": model,
        "text": text,
    }


def list_briefings(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM briefings ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]
