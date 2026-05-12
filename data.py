"""
Mock data generators for the Taiwan AQI multi-agent monitoring system.
All values are synthetic and meant for demo purposes only.
"""

from __future__ import annotations

import math
import random
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

CITIES: list[dict[str, Any]] = [
    # 北部
    {"id": "taipei",     "name": "台北市", "en": "Taipei",     "region": "北部", "lat": 25.03, "lon": 121.57, "bias": 0.95},
    {"id": "new_taipei", "name": "新北市", "en": "New Taipei", "region": "北部", "lat": 25.01, "lon": 121.46, "bias": 1.00},
    {"id": "taoyuan",    "name": "桃園市", "en": "Taoyuan",    "region": "北部", "lat": 24.99, "lon": 121.31, "bias": 1.10},
    {"id": "hsinchu",    "name": "新竹市", "en": "Hsinchu",    "region": "北部", "lat": 24.81, "lon": 120.97, "bias": 0.90},
    {"id": "keelung",    "name": "基隆市", "en": "Keelung",    "region": "北部", "lat": 25.13, "lon": 121.74, "bias": 0.80},
    {"id": "yilan",      "name": "宜蘭縣", "en": "Yilan",      "region": "北部", "lat": 24.76, "lon": 121.75, "bias": 0.55},
    # 中部
    {"id": "miaoli",     "name": "苗栗縣", "en": "Miaoli",     "region": "中部", "lat": 24.56, "lon": 120.82, "bias": 1.00},
    {"id": "taichung",   "name": "台中市", "en": "Taichung",   "region": "中部", "lat": 24.15, "lon": 120.68, "bias": 1.30},
    {"id": "changhua",   "name": "彰化縣", "en": "Changhua",   "region": "中部", "lat": 24.08, "lon": 120.54, "bias": 1.25},
    {"id": "nantou",     "name": "南投縣", "en": "Nantou",     "region": "中部", "lat": 23.96, "lon": 120.97, "bias": 0.85},
    {"id": "yunlin",     "name": "雲林縣", "en": "Yunlin",     "region": "中部", "lat": 23.71, "lon": 120.43, "bias": 1.45},  # 麥寮六輕
    {"id": "chiayi",     "name": "嘉義市", "en": "Chiayi",     "region": "中部", "lat": 23.48, "lon": 120.45, "bias": 1.20},
    # 南部
    {"id": "tainan",     "name": "台南市", "en": "Tainan",     "region": "南部", "lat": 22.99, "lon": 120.21, "bias": 1.25},
    {"id": "kaohsiung",  "name": "高雄市", "en": "Kaohsiung",  "region": "南部", "lat": 22.63, "lon": 120.30, "bias": 1.40},
    {"id": "pingtung",   "name": "屏東縣", "en": "Pingtung",   "region": "南部", "lat": 22.67, "lon": 120.49, "bias": 1.15},
    # 東部
    {"id": "hualien",    "name": "花蓮縣", "en": "Hualien",    "region": "東部", "lat": 23.99, "lon": 121.61, "bias": 0.55},
    {"id": "taitung",    "name": "台東縣", "en": "Taitung",    "region": "東部", "lat": 22.76, "lon": 121.14, "bias": 0.45},
    # 離島
    {"id": "penghu",     "name": "澎湖縣", "en": "Penghu",     "region": "離島", "lat": 23.57, "lon": 119.58, "bias": 0.50},
    {"id": "kinmen",     "name": "金門縣", "en": "Kinmen",     "region": "離島", "lat": 24.45, "lon": 118.38, "bias": 1.20},  # 受陸源影響
    {"id": "matsu",      "name": "連江縣", "en": "Matsu",      "region": "離島", "lat": 26.16, "lon": 119.95, "bias": 1.05},
]

CITY_BY_ID = {c["id"]: c for c in CITIES}

POLLUTANTS = ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]

AQI_LEVELS = [
    {"max":  50, "name": "良好",            "color": "#00e676", "level": 1, "advice": "空氣品質良好，適合戶外活動"},
    {"max": 100, "name": "普通",            "color": "#ffd93d", "level": 2, "advice": "極少數族群可能輕微不適，可正常活動"},
    {"max": 150, "name": "對敏感族群不健康", "color": "#ff8c42", "level": 3, "advice": "敏感族群應減少長時間或激烈戶外活動"},
    {"max": 200, "name": "對所有族群不健康", "color": "#ff4757", "level": 4, "advice": "所有人應減少戶外活動，敏感族群避免外出"},
    {"max": 300, "name": "非常不健康",       "color": "#9b59ff", "level": 5, "advice": "所有族群應留在室內並關閉門窗"},
    {"max": 999, "name": "危害",            "color": "#7f0000", "level": 6, "advice": "緊急狀態，所有人應留在室內"},
]


def aqi_to_level(aqi: float) -> dict[str, Any]:
    for lvl in AQI_LEVELS:
        if aqi <= lvl["max"]:
            return lvl
    return AQI_LEVELS[-1]


# ---------------------------------------------------------------------------
# Time-aware generators
# ---------------------------------------------------------------------------


def _diurnal_factor(hour: int) -> float:
    """Two daily peaks: morning rush (~8am) and evening rush (~6pm)."""
    morning = math.exp(-((hour - 8) ** 2) / 8)
    evening = math.exp(-((hour - 18) ** 2) / 10)
    return 0.7 + 0.45 * (morning + evening)


def _seed_for(city_id: str, ts: datetime) -> int:
    return hash((city_id, ts.strftime("%Y-%m-%d-%H"))) & 0xFFFFFFFF


def generate_current_snapshot(now: datetime | None = None) -> pd.DataFrame:
    """One row per city with the current AQI, pollutants, weather and risk."""
    now = now or datetime.now()
    hour = now.hour
    diurnal = _diurnal_factor(hour)

    rows: list[dict[str, Any]] = []
    for city in CITIES:
        rng = np.random.default_rng(_seed_for(city["id"], now))
        base_aqi = 55 * city["bias"] * diurnal + rng.normal(0, 10)
        aqi = float(max(15, min(280, base_aqi)))

        pm25 = max(2.0, aqi * 0.45 + rng.normal(0, 4))
        pm10 = max(5.0, pm25 * 1.6 + rng.normal(0, 6))
        o3   = max(5.0, 40 + (aqi - 60) * 0.3 + rng.normal(0, 8))
        no2  = max(2.0, 18 + aqi * 0.18 + rng.normal(0, 4))
        so2  = max(0.5, 4 + aqi * 0.03 + rng.normal(0, 1.5))
        co   = max(0.1, 0.4 + aqi * 0.006 + rng.normal(0, 0.1))

        wind_dir = float(rng.uniform(0, 360))
        wind_speed = float(max(0.2, 3 + rng.normal(0, 1.4)))
        humidity = float(max(30, min(95, 70 + rng.normal(0, 8))))
        temperature = float(22 + 6 * math.sin((hour - 6) * math.pi / 12) + rng.normal(0, 1.2))
        pressure = float(1010 + rng.normal(0, 3))

        # Risk score: weighted blend, normalized roughly 0-100
        risk = 0.40 * (pm25 / 35) + 0.20 * (aqi / 150) + 0.15 * (o3 / 100) \
             + 0.10 * (no2 / 80)  + 0.08 * (so2 / 30) + 0.07 * (co / 5)
        risk = float(min(100, max(0, risk * 100)))

        rows.append({
            "city_id": city["id"],
            "city":     city["name"],
            "en":       city["en"],
            "region":   city["region"],
            "lat":      city["lat"],
            "lon":      city["lon"],
            "aqi":      round(aqi, 1),
            "PM2.5":    round(pm25, 1),
            "PM10":     round(pm10, 1),
            "O3":       round(o3, 1),
            "NO2":      round(no2, 1),
            "SO2":      round(so2, 2),
            "CO":       round(co, 2),
            "wind_dir":   round(wind_dir, 0),
            "wind_speed": round(wind_speed, 1),
            "humidity":   round(humidity, 0),
            "temp":       round(temperature, 1),
            "pressure":   round(pressure, 0),
            "risk":       round(risk, 1),
            "level":      aqi_to_level(aqi)["name"],
            "level_num":  aqi_to_level(aqi)["level"],
            "color":      aqi_to_level(aqi)["color"],
            "updated_min_ago": int(rng.integers(1, 12)),
        })
    return pd.DataFrame(rows)


def generate_time_series(hours_back: int = 24, now: datetime | None = None) -> pd.DataFrame:
    """A long-format dataframe of hourly AQI / PM2.5 per city for the last N hours."""
    now = now or datetime.now()
    rows: list[dict[str, Any]] = []
    for h in range(hours_back, -1, -1):
        ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        df = generate_current_snapshot(ts)
        for _, r in df.iterrows():
            rows.append({
                "timestamp": ts,
                "city_id":   r["city_id"],
                "city":      r["city"],
                "region":    r["region"],
                "aqi":       r["aqi"],
                "PM2.5":     r["PM2.5"],
                "PM10":      r["PM10"],
                "O3":        r["O3"],
                "NO2":       r["NO2"],
                "SO2":       r["SO2"],
                "CO":        r["CO"],
                "risk":      r["risk"],
            })
    return pd.DataFrame(rows)


def generate_forecast(city_id: str, hours_ahead: int = 6, now: datetime | None = None) -> pd.DataFrame:
    """Six-hour forecast (mean + lower/upper confidence band) for a single city."""
    now = now or datetime.now()
    rng = np.random.default_rng(_seed_for(city_id + "_fc", now))
    snap = generate_current_snapshot(now)
    base = float(snap.loc[snap["city_id"] == city_id, "aqi"].iloc[0])

    rows = []
    for h in range(1, hours_ahead + 1):
        drift = rng.normal(0, 3)
        diurnal_diff = _diurnal_factor((now.hour + h) % 24) - _diurnal_factor(now.hour)
        val = base + diurnal_diff * 25 + drift * h * 0.6
        spread = 6 + h * 2.5
        rows.append({
            "timestamp": now + timedelta(hours=h),
            "aqi":       round(max(10, val), 1),
            "lower":     round(max(5, val - spread), 1),
            "upper":     round(val + spread, 1),
            "is_forecast": True,
        })
    return pd.DataFrame(rows)


def generate_history_with_forecast(city_id: str, history_hours: int = 12, ahead: int = 6) -> pd.DataFrame:
    now = datetime.now()
    hist_rows = []
    for h in range(history_hours, -1, -1):
        ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        df = generate_current_snapshot(ts)
        v = float(df.loc[df["city_id"] == city_id, "aqi"].iloc[0])
        hist_rows.append({
            "timestamp":   ts,
            "aqi":         v,
            "lower":       v,
            "upper":       v,
            "is_forecast": False,
        })
    fc = generate_forecast(city_id, ahead, now)
    return pd.concat([pd.DataFrame(hist_rows), fc], ignore_index=True)


# ---------------------------------------------------------------------------
# Auxiliary panels
# ---------------------------------------------------------------------------


def generate_citizen_vs_official(now: datetime | None = None, snapshot_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compare Agent A's official EPA readings to Agent D's citizen-sensor scrape."""
    if snapshot_df is not None:
        df = snapshot_df.copy()
        rng = np.random.default_rng(_seed_for("citizen", datetime.now()))
    else:
        now = now or datetime.now()
        df = generate_current_snapshot(now)
        rng = np.random.default_rng(_seed_for("citizen", now))
    df["official_PM2.5"] = df["PM2.5"]
    df["citizen_PM2.5"]  = (df["PM2.5"] + rng.normal(0, 4, len(df))).clip(lower=1).round(1)
    df["delta"]          = (df["citizen_PM2.5"] - df["official_PM2.5"]).round(1)
    return df[["city", "city_id", "official_PM2.5", "citizen_PM2.5", "delta"]]


def generate_satellite_panel(now: datetime | None = None, snapshot_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Synthetic NASA TROPOMI-style satellite columns."""
    if snapshot_df is not None:
        snap = snapshot_df.copy()
        rng = np.random.default_rng(_seed_for("sat", datetime.now()))
    else:
        now = now or datetime.now()
        rng = np.random.default_rng(_seed_for("sat", now))
        snap = generate_current_snapshot(now)
    snap = snap.copy()
    snap["AOD"]   = (0.15 + snap["PM2.5"] / 80 + rng.normal(0, 0.05, len(snap))).clip(lower=0.02).round(3)
    snap["NO2_col"] = (3 + snap["NO2"] * 0.12 + rng.normal(0, 0.4, len(snap))).clip(lower=0.5).round(2)
    snap["SO2_col"] = (0.4 + snap["SO2"] * 0.06 + rng.normal(0, 0.08, len(snap))).clip(lower=0.05).round(3)
    snap["CH4_col"] = (1850 + rng.normal(0, 15, len(snap))).round(1)
    return snap[["city", "AOD", "NO2_col", "SO2_col", "CH4_col"]]


@dataclass
class CleaningReport:
    raw_records:    int
    kept_records:   int
    dropped_records: int
    drop_reasons:   dict[str, int]

    @property
    def keep_rate(self) -> float:
        return self.kept_records / max(1, self.raw_records)


def generate_cleaning_report() -> CleaningReport:
    raw = random.randint(820, 980)
    dropped_invalid = random.randint(15, 40)
    dropped_dup     = random.randint(8, 22)
    dropped_outlier = random.randint(4, 14)
    dropped = dropped_invalid + dropped_dup + dropped_outlier
    return CleaningReport(
        raw_records=raw,
        kept_records=raw - dropped,
        dropped_records=dropped,
        drop_reasons={
            "格式錯誤":  dropped_invalid,
            "重複資料":  dropped_dup,
            "離群值":    dropped_outlier,
        },
    )


# ---------------------------------------------------------------------------
# Health advisory
# ---------------------------------------------------------------------------

SENSITIVE_GROUPS = [
    {"id": "elderly",       "label": "老人",     "icon": "👴"},
    {"id": "children",      "label": "幼童",     "icon": "🧒"},
    {"id": "asthma",        "label": "氣喘患者", "icon": "🫁"},
    {"id": "cardiovascular","label": "心血管",   "icon": "❤️"},
    {"id": "pregnant",      "label": "孕婦",     "icon": "🤰"},
]

GROUP_ADVICE = {
    "elderly":        "避免清晨與傍晚交通尖峰時段外出，外出佩戴 N95 口罩，注意血壓變化。",
    "children":       "暫停戶外體育課與遊戲，改為室內活動，留意是否出現咳嗽或喘鳴。",
    "asthma":         "隨身攜帶吸入器，避免長時間戶外活動，若出現胸悶請立即就醫。",
    "cardiovascular": "減少劇烈運動，PM2.5 與心血管事件高度相關，留意胸痛與心悸。",
    "pregnant":       "盡量待在室內並開啟空氣清淨機，研究顯示 PM2.5 暴露與低出生體重相關。",
}

OUTDOOR_ACTIVITIES = [
    {"id": "running",  "label": "慢跑",     "icon": "🏃"},
    {"id": "cycling",  "label": "自行車",   "icon": "🚴"},
    {"id": "walking",  "label": "散步",     "icon": "🚶"},
    {"id": "hiking",   "label": "登山",     "icon": "🥾"},
    {"id": "commute",  "label": "通勤",     "icon": "🚗"},
    {"id": "outdoor_work", "label": "戶外工作", "icon": "👷"},
]


def best_outdoor_hours(city_id: str) -> pd.DataFrame:
    """Return next 12 hours with a recommendation flag."""
    now = datetime.now()
    rows = []
    for h in range(12):
        ts = now + timedelta(hours=h)
        rng = np.random.default_rng(_seed_for(city_id + "_out", ts))
        diurnal = _diurnal_factor(ts.hour)
        city = CITY_BY_ID[city_id]
        aqi  = 55 * city["bias"] * diurnal + rng.normal(0, 8)
        aqi  = float(max(15, min(220, aqi)))
        rows.append({
            "hour":  ts.strftime("%H:00"),
            "aqi":   round(aqi, 1),
            "level": aqi_to_level(aqi)["name"],
            "color": aqi_to_level(aqi)["color"],
            "score": round(max(0, 100 - aqi * 0.55), 1),
        })
    df = pd.DataFrame(rows)
    df["recommend"] = df["score"] == df["score"].max()
    return df


# ---------------------------------------------------------------------------
# Agent pipeline scripts
# ---------------------------------------------------------------------------

# Visual display order in the lobster theater (left-to-right).
# NOTE: Pipeline execution order is A → D → B → K → C (dependency-driven);
# this list is purely for the desk layout.
AGENTS = [
    {"id": "A", "name": "Agent A · 採集者", "role": "資料採集",   "color": "#00d9ff",
     "desc": "呼叫環保署 API · Open-Meteo 氣象 API"},
    {"id": "B", "name": "Agent B · 分析師", "role": "風險分析",   "color": "#9b59ff",
     "desc": "加權公式 + RAG 文獻 + OpenClaw analyst"},
    {"id": "C", "name": "Agent C · 預警員", "role": "健康預警",   "color": "#00e676",
     "desc": "風險等級轉敏感族群建議"},
    {"id": "D", "name": "Agent D · 爬蟲員", "role": "瀏覽器爬蟲", "color": "#ff8c42",
     "desc": "OpenClaw Browser Agent · 民間感測網路"},
]

CRITIC = {"id": "K", "name": "Critic", "role": "報告驗證",
          "color": "#ffd93d", "desc": "自動審稿，不合格退回 Agent B"}


PIPELINE_STEPS: list[dict[str, Any]] = [
    {"agent": "A", "msg": "GET https://data.moenv.gov.tw/api/v2/aqx_p_432 → 200 OK，取得測站資料",      "wait": 0.45},
    {"agent": "A", "msg": "Open-Meteo 氣象：風向、風速、濕度、溫度合併完成",                            "wait": 0.35},
    {"agent": "D", "msg": "啟動 Chromium Headful Browser，目標：cwbsensor.tw（無官方 API）",          "wait": 0.50},
    {"agent": "D", "msg": "DOM 解析中：locator('table.sensor-grid tr') → 838 筆原始紀錄",            "wait": 0.55},
    {"agent": "D", "msg": "資料清洗：丟棄 67 筆（格式錯誤/重複/離群），保留 771 筆",                    "wait": 0.40},
    {"agent": "B", "msg": "加權公式：0.40·PM2.5 + 0.20·AQI + 0.15·O3 + 0.10·NO2 + 0.08·SO2 + 0.07·CO", "wait": 0.45},
    {"agent": "B", "msg": "RAG 檢索：WHO Air Quality Guidelines 2021、EPA NAAQS、Lancet 2023",       "wait": 0.55},
    {"agent": "B", "msg": "Claude API 生成分析報告（含 4 段文獻引用）",                                "wait": 0.65},
    {"agent": "K", "msg": "Critic 審稿：引用密度 ✓、數值一致性 ✓、結論邏輯 ✓ → 92.4 分通過",            "wait": 0.45},
    {"agent": "C", "msg": "Risk Tier 映射 → 為 10 城市生成敏感族群預警訊息",                          "wait": 0.40},
    {"agent": "C", "msg": "InfluxDB 寫入完成 · 推播至 Webhook · Pipeline 結束",                       "wait": 0.30},
]


# =============================================================================
# Real-time API helpers
# =============================================================================

# Maps Taiwan EPA county names → city IDs used in CITIES list
COUNTY_TO_CITY_ID: dict[str, str] = {
    "臺北市": "taipei",    "台北市": "taipei",
    "新北市": "new_taipei",
    "桃園市": "taoyuan",
    "新竹市": "hsinchu",   "新竹縣": "hsinchu",
    "基隆市": "keelung",
    "宜蘭縣": "yilan",
    "苗栗縣": "miaoli",
    "臺中市": "taichung",  "台中市": "taichung",
    "彰化縣": "changhua",
    "南投縣": "nantou",
    "雲林縣": "yunlin",
    "嘉義市": "chiayi",    "嘉義縣": "chiayi",
    "臺南市": "tainan",    "台南市": "tainan",
    "高雄市": "kaohsiung",
    "屏東縣": "pingtung",
    "花蓮縣": "hualien",
    "臺東縣": "taitung",   "台東縣": "taitung",
    "澎湖縣": "penghu",
    "金門縣": "kinmen",
    "連江縣": "matsu",
}

# One representative city per region for weather fetching (limits Open-Meteo calls to 5)
_REGION_REPR: dict[str, str] = {
    "北部": "taipei",
    "中部": "taichung",
    "南部": "kaohsiung",
    "東部": "hualien",
    "離島": "penghu",
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if not math.isnan(f) else default
    except (TypeError, ValueError):
        return default


def fetch_epa_realtime(api_key: str | None = None) -> pd.DataFrame | None:
    """Fetch real-time AQI from Taiwan 環境部 Open Data v2 (moenv.gov.tw, formerly epa.gov.tw).
    The v2 endpoint requires a registered api_key; returns None on auth or network failure.

    Tolerant to multiple response shapes observed in the wild:
      - {"records": [...], "total": N}        (older)
      - [{...}, {...}]                        (newer array)
      - {"data": [...]}                       (some endpoints)
      - {"result": {"records": [...]}}        (wrapped)
    """
    params: dict[str, Any] = {"limit": 1000, "format": "JSON", "offset": 0}
    if api_key and api_key.strip():
        params["api_key"] = api_key.strip()
    try:
        r = requests.get(
            "https://data.moenv.gov.tw/api/v2/aqx_p_432",
            params=params, timeout=15,
        )
        r.raise_for_status()
        # MOENV returns HTTP 200 + plain-text error body when auth fails.
        ct = r.headers.get("Content-Type", "")
        if "json" not in ct.lower():
            return None
        body = r.json()
        records: list | None = None
        if isinstance(body, list):
            records = body
        elif isinstance(body, dict):
            records = (body.get("records")
                       or body.get("data")
                       or body.get("rows")
                       or (body.get("result", {}) or {}).get("records"))
        if not isinstance(records, list) or not records:
            return None
        return pd.DataFrame(records)
    except Exception:
        return None


def fetch_weather_current(lat: float, lon: float) -> dict[str, float]:
    """Fetch current weather from Open-Meteo (free, no key). Falls back silently."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,surface_pressure",
                "timezone": "Asia/Taipei",
            },
            timeout=8,
        )
        r.raise_for_status()
        c = r.json().get("current", {})
        return {
            "temp":       float(c.get("temperature_2m", 25.0)),
            "humidity":   float(c.get("relative_humidity_2m", 70.0)),
            "wind_speed": float(c.get("wind_speed_10m", 3.0)),
            "wind_dir":   float(c.get("wind_direction_10m", 180.0)),
            "pressure":   float(c.get("surface_pressure", 1013.0)),
        }
    except Exception:
        return {"temp": 25.0, "humidity": 70.0, "wind_speed": 3.0, "wind_dir": 180.0, "pressure": 1013.0}


def _resolve_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """First column name in `candidates` that exists in `df` (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def generate_real_snapshot(epa_key: str | None = None) -> tuple[pd.DataFrame | None, str]:
    """
    Build a per-city snapshot from Taiwan MOENV real-time API + Open-Meteo weather.
    Tolerant to column-name changes between old EPA and new MOENV v2 schema.
    Returns (DataFrame, status_message). DataFrame is None on failure.
    """
    raw = fetch_epa_realtime(epa_key)
    if raw is None or raw.empty:
        return None, "EPA API 無回應或無資料，請確認網路或 API 金鑰"

    # Resolve actual column names once (handles both old & new MOENV schemas)
    cols = {
        "county":   _resolve_col(raw, "County", "county", "縣市"),
        "aqi":      _resolve_col(raw, "AQI", "aqi"),
        "pm25":     _resolve_col(raw, "PM2.5", "pm2.5", "pm25", "PM25"),
        "pm10":     _resolve_col(raw, "PM10", "pm10"),
        "o3":       _resolve_col(raw, "O3", "o3"),
        "no2":      _resolve_col(raw, "NO2", "no2"),
        "so2":      _resolve_col(raw, "SO2", "so2"),
        "co":       _resolve_col(raw, "CO", "co"),
        "wind_dir": _resolve_col(raw, "WindDirec", "winddirec", "wind_direc", "wind_direction"),
    }
    if cols["county"] is None or cols["aqi"] is None:
        return None, f"資料欄位無法識別（缺 County 或 AQI）。實際欄位：{list(raw.columns)[:12]}"

    # Pre-fetch weather for one city per region (5 calls total)
    weather_by_region: dict[str, dict[str, float]] = {}
    for region, rep_id in _REGION_REPR.items():
        rep = CITY_BY_ID[rep_id]
        weather_by_region[region] = fetch_weather_current(rep["lat"], rep["lon"])

    rows: list[dict[str, Any]] = []
    for city in CITIES:
        county_keys = [k for k, v in COUNTY_TO_CITY_ID.items() if v == city["id"]]
        sdf = raw[raw[cols["county"]].isin(county_keys)]
        if sdf.empty:
            continue

        def col_mean(key: str) -> float:
            real = cols.get(key)
            if real is None:
                return 0.0
            vals = pd.to_numeric(sdf[real], errors="coerce").dropna()
            return float(vals.mean()) if len(vals) > 0 else 0.0

        aqi = col_mean("aqi")
        if aqi <= 0:
            continue

        pm25 = max(0.0, col_mean("pm25"))
        pm10 = max(0.0, col_mean("pm10"))
        o3   = max(0.0, col_mean("o3"))
        no2  = max(0.0, col_mean("no2"))
        so2  = max(0.0, col_mean("so2"))
        co   = max(0.0, col_mean("co"))
        wind_dir = col_mean("wind_dir")

        w = weather_by_region.get(city["region"], {"temp": 25.0, "humidity": 70.0, "wind_speed": 3.0, "pressure": 1013.0})

        risk = (0.40 * (pm25 / 35) + 0.20 * (aqi / 150) + 0.15 * (o3 / 100)
              + 0.10 * (no2 / 80)  + 0.08 * (so2 / 30) + 0.07 * (co / 5))
        risk = float(min(100, max(0, risk * 100)))

        rows.append({
            "city_id":    city["id"],
            "city":       city["name"],
            "en":         city["en"],
            "region":     city["region"],
            "lat":        city["lat"],
            "lon":        city["lon"],
            "aqi":        round(aqi, 1),
            "PM2.5":      round(pm25, 1),
            "PM10":       round(pm10, 1),
            "O3":         round(o3, 1),
            "NO2":        round(no2, 1),
            "SO2":        round(so2, 2),
            "CO":         round(co, 2),
            "wind_dir":   round(wind_dir, 0),
            "wind_speed": round(w["wind_speed"], 1),
            "humidity":   round(w["humidity"], 0),
            "temp":       round(w["temp"], 1),
            "pressure":   round(w["pressure"], 0),
            "risk":       round(risk, 1),
            "level":      aqi_to_level(aqi)["name"],
            "level_num":  aqi_to_level(aqi)["level"],
            "color":      aqi_to_level(aqi)["color"],
            "updated_min_ago": 0,
        })

    if not rows:
        return None, "EPA 資料中找不到對應城市，可能 API 格式已變更"
    df = pd.DataFrame(rows)
    return df, f"成功取得 {len(rows)} 城市即時資料（EPA + Open-Meteo）"


def generate_real_timeseries(snapshot: pd.DataFrame, hours_back: int = 24) -> pd.DataFrame:
    """
    Reconstruct plausible 24-hour history anchored to real current AQI values.
    Uses diurnal pattern scaled to the actual current reading.
    """
    now = datetime.now()
    rows: list[dict[str, Any]] = []
    for _, city_row in snapshot.iterrows():
        cid = city_row["city_id"]
        real_aqi = float(city_row["aqi"])
        current_diurnal = max(0.01, _diurnal_factor(now.hour))
        for h in range(hours_back, -1, -1):
            ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
            ratio = _diurnal_factor(ts.hour) / current_diurnal
            base = real_aqi * ratio
            rng = np.random.default_rng(_seed_for(cid + "_rt", ts))
            aqi = float(max(10, base + rng.normal(0, real_aqi * 0.06)))
            pm25 = max(2.0, aqi * 0.45)
            rows.append({
                "timestamp": ts,
                "city_id":   cid,
                "city":      city_row["city"],
                "region":    city_row["region"],
                "aqi":       round(aqi, 1),
                "PM2.5":     round(pm25, 1),
                "PM10":      round(pm25 * 1.6, 1),
                "O3":        round(max(0, 40 + (aqi - 60) * 0.3), 1),
                "NO2":       round(max(0, 18 + aqi * 0.18), 1),
                "SO2":       round(max(0, 4 + aqi * 0.03), 2),
                "CO":        round(max(0, 0.4 + aqi * 0.006), 2),
                "risk":      float(city_row["risk"]),
            })
    return pd.DataFrame(rows)


# =============================================================================
# Direct multi-provider LLM helpers
# (OpenClaw is kept for cron push / Discord-LINE binding / MEMORY.md, but
#  in-app LLM calls go straight to provider HTTP APIs — much faster than
#  routing through OpenClaw gateway which adds 30-60s plugin overhead.)
# =============================================================================

LLM_PROVIDERS: dict[str, dict[str, str]] = {
    "anthropic": {
        "name":          "Anthropic (Claude)",
        "placeholder":   "sk-ant-...",
        "default_model": "claude-sonnet-4-6",
        "base_url":      "",
    },
    # MiniMax has two regional platforms with the same API format but
    # account/key are NOT cross-compatible:
    #   - International (platform.minimaxi.chat) → api.minimaxi.chat
    #   - China         (platform.minimax.chat)  → api.minimax.chat
    # We default to international since that's where MiniMax-M1/M2 lives.
    "minimax": {
        "name":          "MiniMax (國際版)",
        "placeholder":   "eyJ...",
        "default_model": "MiniMax-M2.7",
        "base_url":      "https://api.minimaxi.chat/v1",
    },
    "minimax_cn": {
        "name":          "MiniMax (中國版)",
        "placeholder":   "eyJ...",
        "default_model": "abab6.5s-chat",
        "base_url":      "https://api.minimax.chat/v1",
    },
    "deepseek": {
        "name":          "DeepSeek",
        "placeholder":   "sk-...",
        "default_model": "deepseek-chat",
        "base_url":      "https://api.deepseek.com/v1",
    },
    "openai": {
        "name":          "OpenAI",
        "placeholder":   "sk-...",
        "default_model": "gpt-4o-mini",
        "base_url":      "https://api.openai.com/v1",
    },
    "custom": {
        "name":          "自訂 API（OpenAI 格式）",
        "placeholder":   "...",
        "default_model": "",
        "base_url":      "",
    },
}


# Diagnostic: every call_llm_api updates this so callers can inspect WHY the
# last call failed (timeout / HTTP status / JSON parse / etc).
LAST_LLM_ERROR: str = ""


# Various models leak their internal reasoning as <thinking>...</thinking> or
# <think>...</think> blocks (Claude extended thinking, DeepSeek-R1, Qwen-QwQ,
# some MiniMax). Strip them before showing to the user.
import re as _re

_REASONING_TAG_RE = _re.compile(
    r"<\s*(thinking|think|reasoning|analysis|reflection)\s*>"
    r"[\s\S]*?"
    r"<\s*/\s*\1\s*>",
    _re.IGNORECASE,
)
_DANGLING_OPEN_RE = _re.compile(
    r"<\s*(thinking|think|reasoning|analysis|reflection)\s*>[\s\S]*$",
    _re.IGNORECASE,
)


def clean_llm_output(text: str | None) -> str:
    """Strip reasoning-tag blocks, leading/trailing whitespace, and code fences
    that some models wrap around plain prose."""
    if not text:
        return ""
    out = _REASONING_TAG_RE.sub("", text)
    # If the model started a reasoning block but never closed it (truncated),
    # cut everything from the opening tag to the end.
    out = _DANGLING_OPEN_RE.sub("", out)
    out = out.strip()
    # Drop wrapping ```markdown ... ``` fences if they wrap the whole output
    if out.startswith("```") and out.endswith("```"):
        lines = out.splitlines()
        if len(lines) >= 2:
            out = "\n".join(lines[1:-1]).strip()
    return out


def call_llm_api(
    provider: str,
    api_key: str,
    prompt: str,
    model: str,
    base_url: str = "",
    system: str = "你是台灣空氣品質監測專家，根據 AQI 數據提供準確、有依據的健康建議。回覆請使用繁體中文，簡潔有力。",
    max_tokens: int = 600,
    timeout: int = 30,
) -> str | None:
    """
    Call the selected LLM provider directly via HTTP. Returns response text
    or None on failure. On failure, the module-level `LAST_LLM_ERROR` is set
    to a short diagnostic string (HTTP status / timeout / exception type).
    Anthropic uses Messages API; everything else uses an
    OpenAI-compatible /chat/completions endpoint.
    """
    global LAST_LLM_ERROR
    LAST_LLM_ERROR = ""

    if not api_key or not api_key.strip():
        LAST_LLM_ERROR = "API key 空白"
        return None
    key = api_key.strip()
    mdl = (model or "").strip() or LLM_PROVIDERS.get(provider, {}).get("default_model", "")

    try:
        if provider == "anthropic":
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": mdl or "claude-sonnet-4-6",
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"Anthropic HTTP {r.status_code} · {r.text[:200]}"
                return None
            data = r.json()
            try:
                return clean_llm_output(data["content"][0]["text"])
            except (KeyError, IndexError, TypeError) as e:
                LAST_LLM_ERROR = f"Anthropic 回應解析失敗（{type(e).__name__}）：{str(data)[:200]}"
                return None
        else:
            url = ((base_url or "").strip()
                   or LLM_PROVIDERS.get(provider, {}).get("base_url", "")).rstrip("/")
            if not url:
                LAST_LLM_ERROR = f"{provider} 沒設定 base_url"
                return None
            r = requests.post(
                f"{url}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": mdl,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=timeout,
            )
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"{provider} HTTP {r.status_code} · {r.text[:200]}"
                return None
            data = r.json()
            try:
                return clean_llm_output(data["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as e:
                LAST_LLM_ERROR = f"{provider} 回應解析失敗（{type(e).__name__}）：{str(data)[:200]}"
                return None
    except requests.exceptions.Timeout:
        LAST_LLM_ERROR = f"逾時 >{timeout}s"
        return None
    except requests.exceptions.ConnectionError as e:
        LAST_LLM_ERROR = f"連線失敗：{str(e)[:120]}"
        return None
    except Exception as e:
        LAST_LLM_ERROR = f"{type(e).__name__}: {str(e)[:150]}"
        return None
