"""
本機時序快取 — SQLite-based time-series store for AQI snapshots.

Why SQLite and not InfluxDB?
  - Single-file db, zero install, zero config — friendly for a school demo
  - Python stdlib (no extra deps)
  - The total volume here is tiny: 20 cities × ~10 columns × hourly = ~5k rows/day
    A 1-yr cron pushing hourly is ~175 k rows ~ a few MB. SQLite handles this
    without breaking a sweat. InfluxDB would be overkill.

What's stored
-------------
Two flavours of row, distinguished by `source`:
  - `source = 'pipeline'`     One row per city per Pipeline run (current snapshot).
                              Reflects the user's interactive history.
  - `source = 'cams_hourly'`  Hourly readings from Open-Meteo CAMS past_days=7.
                              Bulk-written each pipeline run (UPSERT keeps it
                              de-duplicated). Used to power "this week's worst
                              AQI" rankings and per-city weekly trends without
                              needing the user to manually run Pipeline 168
                              times before the historical charts have data.

The schema migration below silently upgrades older single-source databases
(no `source` column) by copying rows into the new shape with source='pipeline'.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "lobster_aqi.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS aqi_snapshots (
    ts          TEXT    NOT NULL,
    city_id     TEXT    NOT NULL,
    source      TEXT    NOT NULL DEFAULT 'pipeline',
    city        TEXT    NOT NULL,
    region      TEXT,
    aqi         REAL,
    pm25        REAL,
    pm10        REAL,
    o3          REAL,
    no2         REAL,
    so2         REAL,
    co          REAL,
    risk        REAL,
    data_mode   TEXT,
    PRIMARY KEY (ts, city_id, source)
)
"""

_INDEX_TS    = "CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON aqi_snapshots(ts)"
_INDEX_CITY  = "CREATE INDEX IF NOT EXISTS idx_snapshots_city_ts ON aqi_snapshots(city_id, ts)"
_INDEX_SRC   = "CREATE INDEX IF NOT EXISTS idx_snapshots_source_ts ON aqi_snapshots(source, ts)"


def _migrate_if_needed() -> None:
    """Add the `source` column + new compound PK to older single-source dbs.
    Idempotent — running on a fresh db does nothing because the table is
    created with the new schema in `init()`.
    """
    if not DB_PATH.exists():
        return
    with sqlite3.connect(DB_PATH) as c:
        existing = c.execute("PRAGMA table_info(aqi_snapshots)").fetchall()
        if not existing:
            return  # no table yet, fresh path
        cols = [r[1] for r in existing]
        if "source" in cols:
            return  # already migrated
        # Old schema → migrate by renaming + recreating + copying.
        c.execute("ALTER TABLE aqi_snapshots RENAME TO _aqi_snapshots_v1")
        c.execute(_SCHEMA)
        c.execute(_INDEX_TS)
        c.execute(_INDEX_CITY)
        c.execute(_INDEX_SRC)
        try:
            c.execute(
                "INSERT OR IGNORE INTO aqi_snapshots "
                "(ts, city_id, source, city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode) "
                "SELECT ts, city_id, 'pipeline', city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode "
                "FROM _aqi_snapshots_v1"
            )
        except sqlite3.Error:
            pass
        c.execute("DROP TABLE IF EXISTS _aqi_snapshots_v1")


def init() -> None:
    """Create the db file + table on first use. Idempotent. Also runs the
    legacy migration if an older schema is sitting in the file already."""
    _migrate_if_needed()
    with sqlite3.connect(DB_PATH) as c:
        c.execute(_SCHEMA)
        c.execute(_INDEX_TS)
        c.execute(_INDEX_CITY)
        c.execute(_INDEX_SRC)


# ── Writes ──────────────────────────────────────────────────────────────────

def write_snapshot(
    df: pd.DataFrame,
    data_mode: str = "real",
    source: str = "pipeline",
) -> int:
    """Insert one Pipeline-run snapshot (one row per city). Idempotent on
    `(ts, city_id, source)` PK — re-running the same Pipeline at the same
    second won't bloat the table."""
    if df is None or df.empty:
        return 0
    init()
    ts = datetime.now().isoformat(timespec="seconds")
    rows = [
        (
            ts,
            str(r["city_id"]),
            source,
            str(r["city"]),
            str(r.get("region") or ""),
            float(r["aqi"]),
            float(r["PM2.5"]),
            float(r["PM10"]),
            float(r["O3"]),
            float(r["NO2"]),
            float(r["SO2"]),
            float(r["CO"]),
            float(r["risk"]),
            data_mode,
        )
        for _, r in df.iterrows()
    ]
    with sqlite3.connect(DB_PATH) as c:
        c.executemany(
            "INSERT OR REPLACE INTO aqi_snapshots "
            "(ts, city_id, source, city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def write_history_hourly(
    df: pd.DataFrame,
    source: str = "cams_hourly",
    data_mode: str = "real",
) -> int:
    """Bulk insert hourly history rows (typically from CAMS past_days=7 or
    EPA aqx_p_488). `df` is the long-format frame returned by
    `data.fetch_open_meteo_aq_batch` / `data.fetch_epa_historical` —
    columns: timestamp, city_id, city, region, aqi, PM2.5, PM10, O3, NO2,
    SO2, CO, (risk optional).

    UPSERT means re-running the pipeline never duplicates rows; the same
    hourly point just overwrites with the latest model value."""
    if df is None or df.empty:
        return 0
    init()
    rows = []
    for _, r in df.iterrows():
        ts_val = r.get("timestamp")
        if hasattr(ts_val, "isoformat"):
            ts = ts_val.isoformat(timespec="seconds")
        else:
            ts = str(ts_val) if ts_val is not None else ""
        if not ts:
            continue
        rows.append((
            ts,
            str(r["city_id"]),
            source,
            str(r.get("city") or ""),
            str(r.get("region") or ""),
            float(r.get("aqi") or 0),
            float(r.get("PM2.5") or 0),
            float(r.get("PM10")  or 0),
            float(r.get("O3")    or 0),
            float(r.get("NO2")   or 0),
            float(r.get("SO2")   or 0),
            float(r.get("CO")    or 0),
            float(r.get("risk")  or 0),
            data_mode,
        ))
    if not rows:
        return 0
    with sqlite3.connect(DB_PATH) as c:
        c.executemany(
            "INSERT OR REPLACE INTO aqi_snapshots "
            "(ts, city_id, source, city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


# ── Queries ─────────────────────────────────────────────────────────────────

def read_recent(hours: int = 24, source: str | None = None) -> pd.DataFrame:
    """Pull all rows from the last `hours` hours. Optional source filter."""
    init()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    q = "SELECT * FROM aqi_snapshots WHERE ts >= ?"
    params: list = [cutoff]
    if source:
        q += " AND source = ?"
        params.append(source)
    q += " ORDER BY ts ASC"
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=params)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def city_history(
    city_id: str,
    hours: int = 168,
    sources: list[str] | None = None,
) -> pd.DataFrame:
    """Return one city's hourly history over the last N hours from the
    given sources (defaults to 'cams_hourly' which has the densest data).
    Used by personalization section to chart per-city weekly trends."""
    init()
    if not sources:
        sources = ["cams_hourly"]
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    placeholders = ",".join("?" * len(sources))
    q = (
        f"SELECT ts, aqi, pm25, pm10, o3, no2, so2, co, source "
        f"FROM aqi_snapshots "
        f"WHERE city_id = ? AND ts >= ? AND source IN ({placeholders}) "
        f"ORDER BY ts ASC"
    )
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=[city_id, cutoff, *sources])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def top_cities_by_period(
    hours: int = 168,
    top_n: int = 10,
    sources: list[str] | None = None,
) -> pd.DataFrame:
    """Return cities ranked by their MAX AQI observed in the last `hours`.
    Also returns avg / min for context. Used by the 'weekly AQI ranking'
    card. Defaults to CAMS-hourly data only because that's the densest
    source; pipeline snapshots are sparse (only the user's manual runs)."""
    init()
    if not sources:
        sources = ["cams_hourly"]
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    placeholders = ",".join("?" * len(sources))
    q = (
        f"SELECT city_id, city, "
        f"       ROUND(MAX(aqi), 1) AS max_aqi, "
        f"       ROUND(AVG(aqi), 1) AS avg_aqi, "
        f"       ROUND(MIN(aqi), 1) AS min_aqi, "
        f"       COUNT(*) AS n_hours "
        f"FROM aqi_snapshots "
        f"WHERE ts >= ? AND source IN ({placeholders}) "
        f"GROUP BY city_id, city "
        f"ORDER BY max_aqi DESC "
        f"LIMIT ?"
    )
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=[cutoff, *sources, top_n])
    return df


def city_period_avg(
    city_id: str,
    this_hours: int = 168,
    sources: list[str] | None = None,
) -> tuple[float | None, float | None, int, int]:
    """Compute (this_period_avg, prev_period_avg, this_n, prev_n) where the
    'previous' window is the same width ending where 'this' began.
    Returns (None, None, 0, 0) when not enough data exists.
    Used by personalization section to show '比上週高/低 X%' badges."""
    init()
    if not sources:
        sources = ["cams_hourly"]
    now = datetime.now()
    this_start = (now - timedelta(hours=this_hours)).isoformat(timespec="seconds")
    prev_start = (now - timedelta(hours=2 * this_hours)).isoformat(timespec="seconds")
    prev_end   = this_start
    placeholders = ",".join("?" * len(sources))
    with sqlite3.connect(DB_PATH) as c:
        this_row = c.execute(
            f"SELECT AVG(aqi), COUNT(*) FROM aqi_snapshots "
            f"WHERE city_id=? AND ts >= ? AND source IN ({placeholders})",
            (city_id, this_start, *sources),
        ).fetchone()
        prev_row = c.execute(
            f"SELECT AVG(aqi), COUNT(*) FROM aqi_snapshots "
            f"WHERE city_id=? AND ts >= ? AND ts < ? AND source IN ({placeholders})",
            (city_id, prev_start, prev_end, *sources),
        ).fetchone()
    return (
        float(this_row[0]) if this_row and this_row[0] is not None else None,
        float(prev_row[0]) if prev_row and prev_row[0] is not None else None,
        int(this_row[1]) if this_row else 0,
        int(prev_row[1]) if prev_row else 0,
    )


def total_rows() -> int:
    """Total number of rows in the table (across all sources)."""
    init()
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("SELECT COUNT(*) FROM aqi_snapshots")
        return int(cur.fetchone()[0])


def last_write_time() -> datetime | None:
    """Wall-clock time of the most recent snapshot insert (None if empty)."""
    init()
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("SELECT MAX(ts) FROM aqi_snapshots")
        v = cur.fetchone()[0]
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def stats() -> dict:
    """One-call summary for the sidebar status panel."""
    init()
    with sqlite3.connect(DB_PATH) as c:
        n = int(c.execute("SELECT COUNT(*) FROM aqi_snapshots").fetchone()[0])
        last_ts_row = c.execute("SELECT MAX(ts) FROM aqi_snapshots").fetchone()
        cities_row = c.execute("SELECT COUNT(DISTINCT city_id) FROM aqi_snapshots").fetchone()
        sources_row = c.execute("SELECT COUNT(DISTINCT source) FROM aqi_snapshots").fetchone()
        # Distinct timestamps in 'pipeline' source = number of user runs
        runs_row = c.execute(
            "SELECT COUNT(DISTINCT ts) FROM aqi_snapshots WHERE source = 'pipeline'"
        ).fetchone()
    last_ts = last_ts_row[0] if last_ts_row else None
    return {
        "rows":    n,
        "cities":  int(cities_row[0]) if cities_row else 0,
        "runs":    int(runs_row[0]) if runs_row else 0,
        "sources": int(sources_row[0]) if sources_row else 0,
        "last_write": last_ts,
        "db_path": str(DB_PATH),
    }
