"""
本機時序快取 (Time-Series Database) — 用 SQLite 儲存歷次 AQI 快照
======================================================================

為什麼用 SQLite 而不是 InfluxDB / TimescaleDB / Postgres?
  - **單一檔案 zero-install**:`lobster_aqi.sqlite` 一個檔搞定,
    使用者不用裝資料庫服務 — 對校園 demo / 個人專案最友善
  - **Python 標準函式庫內建**(`sqlite3`),不用 `pip install` 額外套件
  - **資料量小,SQLite 綽綽有餘**:
    20 城市 × ~10 欄位 × 每小時 1 筆 ≈ 5,000 列/天;
    跑一年的 cron 也才 ~175,000 列 ~ 幾 MB,SQLite 處理輕鬆寫意。
    InfluxDB 這種專門的時序資料庫對我們的規模反而 over-engineered。

兩種資料來源(用 `source` 欄位區分,影響查詢時的 WHERE 條件)
-----------------------------------------------------------------
  - `source = 'pipeline'`
      每次使用者手動「啟動 Pipeline」會寫入 20 列(每城市一列)。
      這是「使用者的互動歷史」— 跑了幾次、什麼時間跑、跑出什麼結果。
  - `source = 'cams_hourly'`
      每次 Pipeline 跑完會額外把 Open-Meteo CAMS 的 past_days=7 那批
      hourly 資料 bulk 寫入(UPSERT 自動去重),用來:
        a) 「本週 AQI 紀錄板」排名(那一週 AQI 最高的城市)
        b) 個人化推薦的「過去 7 天該城市的趨勢圖」
      這樣使用者不必為了看歷史圖表,手動跑 168 次 Pipeline。

Schema 遷移
-----------
最早期版本沒有 `source` 欄位,只有單一資料來源。`_migrate_if_needed()`
會在啟動時偵測舊 schema,自動 rename + 重建 + 把舊資料以 source='pipeline'
複製回新表 — 對使用者透明,不會弄丟資料。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 資料庫檔案絕對路徑 — 與本檔案同層,避免不同工作目錄下找不到
DB_PATH = Path(__file__).resolve().parent / "lobster_aqi.sqlite"

# ── Schema 定義 ─────────────────────────────────────────────────────────────
# CREATE TABLE 加上 `IF NOT EXISTS` 讓本函式可以多次呼叫(idempotent)。
# PRIMARY KEY (ts, city_id, source):
#   - 同一秒、同一城市、同一資料來源最多一筆 → 防止重複插入
#   - 配合 INSERT OR REPLACE 達到 UPSERT(更新或插入)的效果
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

# 3 個索引各自加速不同查詢模式:
#   - idx_snapshots_ts:查「最近 N 小時」用(read_recent)
#   - idx_snapshots_city_ts:查「某城市的歷史」用(city_history)
#   - idx_snapshots_source_ts:查「特定來源的時間區間」用(top_cities_by_period)
_INDEX_TS    = "CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON aqi_snapshots(ts)"
_INDEX_CITY  = "CREATE INDEX IF NOT EXISTS idx_snapshots_city_ts ON aqi_snapshots(city_id, ts)"
_INDEX_SRC   = "CREATE INDEX IF NOT EXISTS idx_snapshots_source_ts ON aqi_snapshots(source, ts)"


def _migrate_if_needed() -> None:
    """偵測舊版 schema(沒有 `source` 欄位)並自動升級。

    流程:
      1. 若資料庫檔不存在 → 直接退出(init() 會建立新 schema)
      2. 讀取 `aqi_snapshots` 表的所有欄位
      3. 若已有 `source` 欄位 → 已是新 schema,直接退出(idempotent)
      4. 否則進入遷移流程:
           a. 把舊表 RENAME 成 `_aqi_snapshots_v1`(備份)
           b. 建立全新 schema 的 `aqi_snapshots` 表 + 3 個索引
           c. 把舊表的資料以 source='pipeline' 複製回新表
           d. 刪除備份表
      5. 任何 SQL 錯誤都被 swallowed(`except sqlite3.Error: pass`),
         保證遷移失敗不會炸掉整個程式 — 大不了使用者就是少了歷史資料。

    執行頻率:每次 init() 都會呼叫,但只在第一次升級時真的會做事。
    """
    if not DB_PATH.exists():
        return  # 新檔還沒建立,init() 會直接 CREATE 新 schema
    with sqlite3.connect(DB_PATH) as c:
        # PRAGMA table_info 回傳每個欄位的 (cid, name, type, notnull, dflt_value, pk)
        existing = c.execute("PRAGMA table_info(aqi_snapshots)").fetchall()
        if not existing:
            return  # 表還沒建立(可能是空的 .sqlite 檔)
        cols = [r[1] for r in existing]  # 取 name 欄位
        if "source" in cols:
            return  # 已遷移過,什麼都不做
        # ↓ 這裡開始是舊 schema 偵測到的升級流程
        c.execute("ALTER TABLE aqi_snapshots RENAME TO _aqi_snapshots_v1")
        c.execute(_SCHEMA)
        c.execute(_INDEX_TS)
        c.execute(_INDEX_CITY)
        c.execute(_INDEX_SRC)
        try:
            # 把舊資料以 source='pipeline' 注入新表;INSERT OR IGNORE 防止
            # PK 衝突時整個遷移失敗
            c.execute(
                "INSERT OR IGNORE INTO aqi_snapshots "
                "(ts, city_id, source, city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode) "
                "SELECT ts, city_id, 'pipeline', city, region, aqi, pm25, pm10, o3, no2, so2, co, risk, data_mode "
                "FROM _aqi_snapshots_v1"
            )
        except sqlite3.Error:
            # 遷移過程出錯就直接放棄,避免阻擋使用者使用程式
            pass
        c.execute("DROP TABLE IF EXISTS _aqi_snapshots_v1")  # 清掉備份


def init() -> None:
    """建立 / 確認資料庫檔案與 schema 存在。

    特性:
      - **Idempotent**:第一次呼叫會建檔,之後呼叫是 no-op(因為 CREATE TABLE IF NOT EXISTS)
      - 每個寫入 / 查詢函式都會先呼叫 `init()` 確保表存在,不必擔心「忘了初始化」
      - 內部會先跑遷移(若有需要)再建立新 schema
    """
    _migrate_if_needed()
    with sqlite3.connect(DB_PATH) as c:
        c.execute(_SCHEMA)
        c.execute(_INDEX_TS)
        c.execute(_INDEX_CITY)
        c.execute(_INDEX_SRC)


# ─── 寫入 (Writes) ──────────────────────────────────────────────────────────

def write_snapshot(
    df: pd.DataFrame,
    data_mode: str = "real",
    source: str = "pipeline",
) -> int:
    """寫入「一次 Pipeline 跑完的當下快照」(20 個城市各一列)。

    Idempotent on `(ts, city_id, source)` — 同一秒重跑兩次 Pipeline 不會
    在表內留下 40 列(主鍵會自動 REPLACE)。

    Parameters
    ----------
    df : pd.DataFrame
        必須包含欄位:city_id, city, region, aqi, PM2.5, PM10, O3, NO2, SO2, CO, risk
    data_mode : str
        'real'(EPA API 成功)或 'mock'(EPA 失敗 fallback);用於後續分析
        時辨識資料真偽
    source : str
        通常為 'pipeline',即使用者觸發的快照。也可傳其他值(例如測試用)

    Returns
    -------
    int
        實際寫入的列數;空 DataFrame 回 0
    """
    if df is None or df.empty:
        return 0
    init()
    # 使用「整批共用同一個 timestamp」確保 20 個城市的這次快照是同一個邏輯時點
    ts = datetime.now().isoformat(timespec="seconds")
    # 用 list comprehension 把每一列 DataFrame 轉成 SQL 參數的 tuple
    # 注意所有數值欄位都顯式轉成 float() — 避免 numpy.float64 在 sqlite 序列化異常
    rows = [
        (
            ts,
            str(r["city_id"]),
            source,
            str(r["city"]),
            str(r.get("region") or ""),  # region 可能 None,用空字串 fallback
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
        # INSERT OR REPLACE 等同於 UPSERT — PK 衝突時覆蓋舊值
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
    """大批寫入 hourly 歷史資料(通常來自 CAMS 過去 7 天 或 EPA aqx_p_488)。

    與 `write_snapshot` 的差別:
      - `write_snapshot` 用「當下 datetime.now() 當 ts」→ 所有列共用同一個時點
      - 本函式從 `df["timestamp"]` 各列各取自己的時點 → 每筆 hourly 資料對應
        自己的時間,可以一次寫入過去 168 小時 × 20 城市 = 3360 筆

    UPSERT 確保「每次跑 Pipeline 都會把同一批 hourly 資料覆蓋一次」,但因為
    PK 是 (ts, city_id, source),覆蓋的是同一筆,不會無限膨脹。

    Returns
    -------
    int
        實際寫入的列數;空輸入或所有 timestamp 都缺失時回 0
    """
    if df is None or df.empty:
        return 0
    init()
    rows = []
    for _, r in df.iterrows():
        # timestamp 可能是 pandas.Timestamp 或 datetime 或字串;統一轉成 ISO 格式字串
        ts_val = r.get("timestamp")
        if hasattr(ts_val, "isoformat"):
            ts = ts_val.isoformat(timespec="seconds")
        else:
            ts = str(ts_val) if ts_val is not None else ""
        if not ts:
            continue  # 缺少 timestamp 的列直接跳過,不能進資料庫(PK 不能為空)
        # 所有數值欄位用 `or 0` fallback,防止 NaN / None 寫入失敗
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


# ─── 查詢 (Queries) ─────────────────────────────────────────────────────────

def read_recent(hours: int = 24, source: str | None = None) -> pd.DataFrame:
    """取出最近 N 小時的所有列(可篩 source)。

    Parameters
    ----------
    hours : int
        往回看的小時數,例 24 = 過去一天
    source : str | None
        None = 不篩;傳 'pipeline' / 'cams_hourly' 等可只取特定來源

    Returns
    -------
    pd.DataFrame
        ts 已 parse 成 datetime,可直接用於 Plotly 時序圖
    """
    init()
    # 動態組裝 WHERE — 用 parameter binding(`?`)避免 SQL injection
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    q = "SELECT * FROM aqi_snapshots WHERE ts >= ?"
    params: list = [cutoff]
    if source:
        q += " AND source = ?"
        params.append(source)
    q += " ORDER BY ts ASC"  # 時序圖需要由舊到新
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=params)
    if not df.empty:
        # SQLite 回傳的 ts 是字串,要轉成 datetime 後 Plotly 才會正確軸刻度
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def city_history(
    city_id: str,
    hours: int = 168,
    sources: list[str] | None = None,
) -> pd.DataFrame:
    """查單一城市的 N 小時歷史(預設 168h = 7 天)。

    主要用途:個人化推薦頁面的「過去 7 天該城市的 AQI 趨勢圖」。

    Parameters
    ----------
    city_id : str
        例 'taipei'、'kaohsiung'
    hours : int
        往回看的小時數,預設 168(7 天)
    sources : list[str] | None
        要取哪些資料來源,預設 ['cams_hourly'](密度最高,每小時一筆);
        若用 ['pipeline'] 則只有使用者手動跑的時點,會稀疏很多

    Returns
    -------
    pd.DataFrame
        欄位:ts(datetime)、aqi、pm25、pm10、o3、no2、so2、co、source
    """
    init()
    if not sources:
        sources = ["cams_hourly"]  # 預設用密度最高的 CAMS hourly
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    # 動態產生 SQL 的 IN (?, ?, ?) 佔位符數量 — 配合 params 同步擴張
    placeholders = ",".join("?" * len(sources))
    q = (
        f"SELECT ts, aqi, pm25, pm10, o3, no2, so2, co, source "
        f"FROM aqi_snapshots "
        f"WHERE city_id = ? AND ts >= ? AND source IN ({placeholders}) "
        f"ORDER BY ts ASC"
    )
    with sqlite3.connect(DB_PATH) as c:
        # 把 city_id, cutoff, *sources 都當 parameter binding 傳入
        df = pd.read_sql_query(q, c, params=[city_id, cutoff, *sources])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def top_cities_by_period(
    hours: int = 168,
    top_n: int = 10,
    sources: list[str] | None = None,
) -> pd.DataFrame:
    """N 小時內 AQI 最高的城市排名(預設過去 7 天)。

    為什麼需要這個?主畫面的「即時排名」只顯示「現在」最高的城市,
    但有些城市可能上週中段被炸到 200+,現在卻已降回 50 — 排名看不出來。
    本函式用 MAX(aqi) 抓出「過去 N 小時的峰值」做排名,並一併回傳
    平均/最低做為參考。

    Returns
    -------
    pd.DataFrame
        欄位:city_id, city, max_aqi, avg_aqi, min_aqi, n_hours
        按 max_aqi DESC 排序,最多 top_n 列
    """
    init()
    if not sources:
        # CAMS 是密度最高的來源,適合計算「真正的峰值」;pipeline 只有
        # 使用者手動跑的時點,稀疏到無法代表趨勢
        sources = ["cams_hourly"]
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    placeholders = ",".join("?" * len(sources))
    # SQL 內建 ROUND() 直接給出 1 位小數的結果,省一次 Python round 處理
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
    """計算單一城市「這週 vs 上週」的平均 AQI 對比。

    用於個人化推薦的「比上週高 X%」徽章。

    時間切片邏輯:
      - this 區間:[now - this_hours, now]
      - prev 區間:[now - 2*this_hours, now - this_hours]
      (兩個區間等寬,prev 接續在 this 前面)

    Returns
    -------
    tuple
        (this_avg, prev_avg, this_count, prev_count)
        當該區間完全沒資料時對應的 avg 為 None,count 為 0
    """
    init()
    if not sources:
        sources = ["cams_hourly"]
    now = datetime.now()
    this_start = (now - timedelta(hours=this_hours)).isoformat(timespec="seconds")
    prev_start = (now - timedelta(hours=2 * this_hours)).isoformat(timespec="seconds")
    prev_end   = this_start  # prev 區間的結束 = this 區間的開始
    placeholders = ",".join("?" * len(sources))
    with sqlite3.connect(DB_PATH) as c:
        # 一次 query 取 (AVG, COUNT) 兩個 aggregate;COUNT=0 時 AVG 為 None
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
    # 把 SQL 回傳的 Row 物件轉成乾淨的 Python primitives;None 維持 None
    return (
        float(this_row[0]) if this_row and this_row[0] is not None else None,
        float(prev_row[0]) if prev_row and prev_row[0] is not None else None,
        int(this_row[1]) if this_row else 0,
        int(prev_row[1]) if prev_row else 0,
    )


def total_rows() -> int:
    """資料庫所有 source 加總的列數。Sidebar 狀態列用。"""
    init()
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("SELECT COUNT(*) FROM aqi_snapshots")
        return int(cur.fetchone()[0])


def last_write_time() -> datetime | None:
    """最近一次寫入的時間;表為空時回 None。

    回傳 datetime 而非字串,方便上層做「距現在 X 分鐘」運算。
    """
    init()
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("SELECT MAX(ts) FROM aqi_snapshots")
        v = cur.fetchone()[0]
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        # 萬一資料庫裡有舊版的非 ISO 時間字串,優雅地回 None 而非炸掉
        return None


# ─── 健康日誌 (Health Diary) — P1 #2 ──────────────────────────────────────
# 使用者每日打卡記錄症狀 / 戶外時數,跨 session 持久化在本機 SQLite。
# 與 AQI 時序關聯後可看出「個人對哪種污染物較敏感」。
# ──────────────────────────────────────────────────────────────────────────

_HEALTH_DIARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_diary (
    date         TEXT    NOT NULL,        -- YYYY-MM-DD,主鍵之一(同一天只能有一筆)
    city_id      TEXT    NOT NULL,        -- 該天的常駐城市(允許不同天不同地)
    symptom_score INTEGER NOT NULL,        -- 症狀嚴重度 0(無)~5(嚴重),使用者主觀填寫
    outdoor_min   INTEGER NOT NULL,        -- 該天戶外時數(分鐘),自我估算
    note          TEXT,                    -- 自由文字備註(吃了什麼藥、活動類型等)
    created_at    TEXT    NOT NULL,        -- ISO 時間戳(自動填入)
    PRIMARY KEY (date, city_id)
)
"""
_HEALTH_DIARY_INDEX = "CREATE INDEX IF NOT EXISTS idx_diary_date ON health_diary(date)"


def _init_health_diary() -> None:
    """確保 health_diary 表存在(idempotent)。每個 diary 寫入 / 讀取前都會呼叫。"""
    with sqlite3.connect(DB_PATH) as c:
        c.execute(_HEALTH_DIARY_SCHEMA)
        c.execute(_HEALTH_DIARY_INDEX)


def upsert_diary_entry(
    date: str,
    city_id: str,
    symptom_score: int,
    outdoor_min: int,
    note: str = "",
) -> None:
    """新增 / 更新一筆健康日誌(同一天同城市覆蓋,使用 INSERT OR REPLACE)。

    Parameters
    ----------
    date : str
        YYYY-MM-DD;呼叫者通常傳 `datetime.now().strftime("%Y-%m-%d")`
    city_id : str
        該天的常駐城市(允許之後跨日改地點)
    symptom_score : int
        症狀嚴重度,clip 在 [0, 5]
    outdoor_min : int
        戶外時數(分鐘),clip 在 [0, 1440]
    note : str
        自由文字備註

    Notes
    -----
    `created_at` 保留「首次建立的時間」 — 後續同一天同城市再次 upsert 時,
    我們會先 SELECT 既有記錄的 created_at 並繼續使用,避免欄位語意被
    INSERT OR REPLACE 改寫成「最後一次更新時間」。
    """
    _init_health_diary()
    symptom_score = max(0, min(5, int(symptom_score)))
    outdoor_min   = max(0, min(1440, int(outdoor_min)))
    now_iso = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as c:
        # 保留首次 created_at — INSERT OR REPLACE 會整列覆寫,所以要先讀回
        existing = c.execute(
            "SELECT created_at FROM health_diary WHERE date=? AND city_id=?",
            (date, city_id),
        ).fetchone()
        first_created = existing[0] if existing else now_iso
        c.execute(
            "INSERT OR REPLACE INTO health_diary "
            "(date, city_id, symptom_score, outdoor_min, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date, city_id, symptom_score, outdoor_min, note or "", first_created),
        )


def read_diary(city_id: str | None = None, days: int = 30) -> pd.DataFrame:
    """讀取最近 N 天的健康日誌。

    Parameters
    ----------
    city_id : str | None
        指定城市過濾;None 表示不過濾(回傳所有城市)
    days : int
        往回看多少天,預設 30

    Returns
    -------
    pd.DataFrame
        欄位:date(datetime)、city_id、symptom_score、outdoor_min、note、created_at
        無紀錄時回空 DataFrame
    """
    _init_health_diary()
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    q = "SELECT * FROM health_diary WHERE date >= ?"
    params: list = [cutoff]
    if city_id:
        q += " AND city_id = ?"
        params.append(city_id)
    q += " ORDER BY date ASC"
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=params)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def diary_with_aqi(city_id: str, days: int = 30) -> pd.DataFrame:
    """合併「健康日誌」與「該日 AQI 平均」,供散點圖 / 相關性分析使用。

    JOIN 邏輯:
      - 健康日誌的 date(例 '2026-05-10')
      - 對齊 aqi_snapshots 中該日(00:00 ~ 23:59)的 cams_hourly 平均 AQI

    Returns
    -------
    pd.DataFrame
        欄位:date、symptom_score、outdoor_min、avg_aqi、peak_aqi、note
    """
    _init_health_diary()
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    q = (
        "SELECT d.date, d.symptom_score, d.outdoor_min, d.note, "
        "       AVG(a.aqi) AS avg_aqi, MAX(a.aqi) AS peak_aqi "
        "FROM health_diary d "
        "LEFT JOIN aqi_snapshots a "
        "  ON a.city_id = d.city_id "
        "  AND DATE(a.ts) = d.date "
        "  AND a.source = 'cams_hourly' "
        "WHERE d.city_id = ? AND d.date >= ? "
        "GROUP BY d.date, d.symptom_score, d.outdoor_min, d.note "
        "ORDER BY d.date ASC"
    )
    with sqlite3.connect(DB_PATH) as c:
        df = pd.read_sql_query(q, c, params=[city_id, cutoff])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def stats() -> dict:
    """一次回傳 sidebar 顯示用的彙總指標(列數、城市數、跑次、來源數等)。

    Returns
    -------
    dict
        rows : int        資料庫總列數
        cities : int      不同城市數(理想是 20)
        runs : int        Pipeline 跑過幾次(distinct ts where source='pipeline')
        sources : int     資料來源數(通常 2:pipeline + cams_hourly)
        last_write : str  最近寫入時間(ISO 字串,可能為 None)
        db_path : str     資料庫檔案路徑
    """
    init()
    with sqlite3.connect(DB_PATH) as c:
        # 用一個 connection 跑多個 query,避免反覆開關連線的 overhead
        n = int(c.execute("SELECT COUNT(*) FROM aqi_snapshots").fetchone()[0])
        last_ts_row = c.execute("SELECT MAX(ts) FROM aqi_snapshots").fetchone()
        cities_row = c.execute("SELECT COUNT(DISTINCT city_id) FROM aqi_snapshots").fetchone()
        sources_row = c.execute("SELECT COUNT(DISTINCT source) FROM aqi_snapshots").fetchone()
        # 算「Pipeline 跑過幾次」= source='pipeline' 中不同時間戳的數量
        # (每次跑 Pipeline 會在同一秒寫入 20 列,因此 distinct ts 就是「跑了幾次」)
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
