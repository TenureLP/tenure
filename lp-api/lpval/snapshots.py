"""Fee-growth snapshots per (pool, range), so fee rates do not depend on an archive node.

Every valuation records one snapshot for free. A cron calling `python3 -m lpval snapshot <ids...>` keeps
a watchlist warm.
"""

import os
import sqlite3
import time

_PATH = os.environ.get("LPVAL_SNAP_DB", "lpval_snapshots.sqlite")
MIN_AGE_SECONDS = 300
MIN_SPACING_SECONDS = 60


def _conn():
    c = sqlite3.connect(_PATH, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute(
        "CREATE TABLE IF NOT EXISTS snap (pool TEXT, tl INTEGER, tu INTEGER, ts INTEGER, fg0 TEXT, fg1 TEXT)"
    )
    # UNIQUE is what actually enforces the spacing: the SELECT-then-INSERT below is a race, and
    # concurrent callers all read the same stale maximum and all insert.
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS snap_idx ON snap (pool, tl, tu, ts)")
    return c


def record(pool_id: str, tl: int, tu: int, fg0: int, fg1: int, now: int = None):
    now = int(now or time.time())
    with _conn() as c:
        last = c.execute(
            "SELECT MAX(ts) FROM snap WHERE pool=? AND tl=? AND tu=?", (pool_id, tl, tu)
        ).fetchone()[0]
        if last is None or now - last >= MIN_SPACING_SECONDS:
            c.execute(
                "INSERT OR IGNORE INTO snap VALUES (?,?,?,?,?,?)", (pool_id, tl, tu, now, str(fg0), str(fg1))
            )


def oldest_within(pool_id: str, tl: int, tu: int, lookback_seconds: float, now: int = None):
    """Oldest snapshot inside the lookback window that is at least MIN_AGE_SECONDS old."""
    now = int(now or time.time())
    with _conn() as c:
        row = c.execute(
            "SELECT ts, fg0, fg1 FROM snap WHERE pool=? AND tl=? AND tu=? AND ts>=? AND ts<=? ORDER BY ts ASC LIMIT 1",
            (pool_id, tl, tu, now - int(lookback_seconds), now - MIN_AGE_SECONDS),
        ).fetchone()
    return (row[0], int(row[1]), int(row[2])) if row else None
