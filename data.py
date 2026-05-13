"""
Mock data generators for the Taiwan AQI multi-agent monitoring system.
All values are synthetic and meant for demo purposes only.
"""

from __future__ import annotations

# Use the OS certificate store (Windows / macOS keychain) instead of certifi's
# bundled CA list. Required for environments where OpenSSL 3.5+ rejects certs
# missing the Subject Key Identifier extension (e.g. Taiwan MOENV's TWCA cert).
# Must run BEFORE `import requests` so urllib3's SSL context picks it up.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import json
import math
import random
import time
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def _open_meteo_city_slice(
    city_id: str,
    past_days: int = 1,
    forecast_days: int = 1,
) -> pd.DataFrame | None:
    """Single-city Open-Meteo Air Quality slice — used by the forecast +
    history-with-forecast helpers below. Returns a DataFrame with
    `timestamp, aqi, is_forecast` (the columns the existing chart code
    expects)."""
    city = CITY_BY_ID.get(city_id)
    if city is None:
        return None
    df = fetch_open_meteo_aq_batch([city], past_days=past_days, forecast_days=forecast_days)
    if df is None or df.empty:
        return None
    df = df[df["city_id"] == city_id].dropna(subset=["aqi"]).sort_values("timestamp")
    return df


def generate_forecast(city_id: str, hours_ahead: int = 6, now: datetime | None = None) -> pd.DataFrame:
    """N-hour AQI forecast from Open-Meteo Copernicus CAMS.
    Returns columns: timestamp, aqi, lower, upper, is_forecast.
    Confidence band widens linearly with the forecast horizon
    (a stand-in for true model uncertainty — CAMS doesn't ship per-hour σ
    via the free endpoint)."""
    base = _open_meteo_city_slice(city_id, past_days=0, forecast_days=2)
    if base is None or base.empty:
        return pd.DataFrame(columns=["timestamp", "aqi", "lower", "upper", "is_forecast"])
    now_ts = pd.Timestamp(now or datetime.now())
    fc = base[base["timestamp"] > now_ts].head(hours_ahead).copy()
    fc = fc[["timestamp", "aqi"]].reset_index(drop=True)
    fc["is_forecast"] = True
    # Confidence band: widen by 2 AQI/hr from a 6-point floor
    spread = 6 + (fc.index.to_series() + 1) * 2.5
    fc["lower"] = (fc["aqi"] - spread).clip(lower=5).round(1)
    fc["upper"] = (fc["aqi"] + spread).round(1)
    return fc


def generate_history_with_forecast(city_id: str, history_hours: int = 12, ahead: int = 6) -> pd.DataFrame:
    """Past N hours + next M hours for a city, both from Open-Meteo CAMS.
    Used by the city-deep-dive forecast chart."""
    base = _open_meteo_city_slice(city_id, past_days=2, forecast_days=2)
    if base is None or base.empty:
        return pd.DataFrame(columns=["timestamp", "aqi", "lower", "upper", "is_forecast"])
    now_ts = pd.Timestamp(datetime.now())
    hist = base[base["timestamp"] <= now_ts].tail(history_hours + 1).copy()
    hist = hist[["timestamp", "aqi"]].copy()
    hist["lower"] = hist["aqi"]
    hist["upper"] = hist["aqi"]
    hist["is_forecast"] = False

    fc = base[base["timestamp"] > now_ts].head(ahead).copy()
    fc = fc[["timestamp", "aqi"]].reset_index(drop=True)
    fc["is_forecast"] = True
    spread = 6 + (fc.index.to_series() + 1) * 2.5
    fc["lower"] = (fc["aqi"] - spread).clip(lower=5).round(1)
    fc["upper"] = (fc["aqi"] + spread).round(1)

    return pd.concat([hist, fc], ignore_index=True)


# ---------------------------------------------------------------------------
# Auxiliary panels
# ---------------------------------------------------------------------------


def generate_citizen_vs_official(
    snapshot_df: pd.DataFrame,
    lass_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compare official EPA PM2.5 (from the snapshot) against the
    LASS-net civilian-sensor median per city (from `fetch_lass_airbox()`).

    `lass_df` is the per-city DataFrame returned by `fetch_lass_airbox()`.
    If None or empty, the comparison falls back to `citizen_PM2.5 = NaN`
    everywhere — the UI will then show "無民間感測站覆蓋" for each city.
    """
    df = snapshot_df[["city", "city_id", "PM2.5"]].copy()
    df = df.rename(columns={"PM2.5": "official_PM2.5"})

    if lass_df is not None and not lass_df.empty:
        df = df.merge(
            lass_df[["city_id", "citizen_PM2.5", "sensor_count"]],
            on="city_id",
            how="left",
        )
    else:
        df["citizen_PM2.5"] = float("nan")
        df["sensor_count"]  = 0

    df["delta"] = (df["citizen_PM2.5"] - df["official_PM2.5"]).round(1)
    return df[["city", "city_id", "official_PM2.5", "citizen_PM2.5", "delta", "sensor_count"]]


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
# Pipeline execution order: A (採集 — 含資料來源 + 清洗) → B (分析) → C (預警).
# Previously this list had 4 agents (A/B/C + 民間感測員 D) plus a separate
# CRITIC; the 民間感測員 was merged into 採集者 because both were doing pure
# HTTP fetching with vestigial LLM "comment" calls, and the Critic was
# removed because its score didn't actually gate anything (low scores
# never triggered a retry of the analyst).
AGENTS = [
    {"id": "A", "name": "採集者", "role": "資料採集",   "color": "#00d9ff",
     "desc": "EPA + Open-Meteo + 民生公共物聯網 / LASS（並行清洗，無 LLM）"},
    {"id": "B", "name": "分析師", "role": "風險分析",   "color": "#9b59ff",
     "desc": "加權公式 + RAG 文獻檢索 + LLM 風險報告"},
    {"id": "C", "name": "預警員", "role": "健康預警",   "color": "#00e676",
     "desc": "風險等級 → 5 類敏感族群建議"},
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
        "county":      _resolve_col(raw, "County", "county", "縣市"),
        "aqi":         _resolve_col(raw, "AQI", "aqi"),
        "pm25":        _resolve_col(raw, "PM2.5", "pm2.5", "pm25", "PM25"),
        "pm10":        _resolve_col(raw, "PM10", "pm10"),
        "o3":          _resolve_col(raw, "O3", "o3"),
        "no2":         _resolve_col(raw, "NO2", "no2"),
        "so2":         _resolve_col(raw, "SO2", "so2"),
        "co":          _resolve_col(raw, "CO", "co"),
        "wind_dir":    _resolve_col(raw, "WindDirec", "winddirec", "wind_direc", "wind_direction"),
        "publishtime": _resolve_col(raw, "publishtime", "PublishTime", "datacreationdate"),
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

        # Compute minutes-since-publish from EPA's publishtime/datacreationdate
        # so the "資料新鮮度" cards reflect actual EPA station update lag,
        # rather than displaying "0 分鐘前" for every city.
        publish_col = cols.get("publishtime")
        if publish_col is not None and publish_col in sdf.columns:
            pub_dt = pd.to_datetime(sdf[publish_col], errors="coerce").max()
            if pd.notna(pub_dt):
                # EPA timestamps are in UTC+8 without timezone tag — strip tz from now
                delta_min = max(0, int((datetime.now() - pub_dt.to_pydatetime()).total_seconds() // 60))
                updated_min = min(delta_min, 999)
            else:
                updated_min = 0
        else:
            updated_min = 0

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
            "updated_min_ago": updated_min,
        })

    if not rows:
        return None, "EPA 資料中找不到對應城市，可能 API 格式已變更"
    df = pd.DataFrame(rows)
    return df, f"成功取得 {len(rows)} 城市即時資料（EPA + Open-Meteo）"


def generate_real_timeseries(
    snapshot: pd.DataFrame,
    hours_back: int = 24,
    epa_key: str | None = None,
) -> pd.DataFrame:
    """Build a 24-hour history DataFrame.

    Strategy (in order of preference, each falls back to the next):
      1. EPA aqx_p_488 — official Taiwan EPA hourly history.
      2. Open-Meteo CAMS — Copernicus atmospheric model hourly history.
      3. Diurnal-pattern reconstruction (clearly labelled as derived).

    The synthesised fallback (3) is only used as a last resort when both
    external sources fail. It is anchored to the current AQI reading so
    at least the right-hand "now" edge matches reality.
    """
    # 1. EPA history (real Taiwan readings)
    if epa_key:
        epa_hist = fetch_epa_historical(epa_key, hours_back=hours_back)
        if epa_hist is not None and not epa_hist.empty:
            return epa_hist

    # 2. Open-Meteo CAMS (real model)
    cams = fetch_open_meteo_aq_batch(CITIES, past_days=1, forecast_days=0)
    if cams is not None and not cams.empty:
        return cams[cams["timestamp"] <= pd.Timestamp(datetime.now())].copy()

    # 3. Fallback: diurnal-pattern reconstruction
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
# Real-data fetchers — replace the synthetic generators above
# =============================================================================

LASS_AIRBOX_URL    = "https://pm25.lass-net.org/data/last-all-airbox.json"
EPA_HIST_URL       = "https://data.moenv.gov.tw/api/v2/aqx_p_488"
OPEN_METEO_AQ_URL  = "https://air-quality-api.open-meteo.com/v1/air-quality"

# 民生公共物聯網 (Civil IoT Taiwan) — Smart City PM2.5 dense sensor network.
# Official OGC SensorThings API at the Academia Sinica colife.org.tw mirror.
# This is the proper "民生公共物聯網" data service endpoint — covers ~10,000+
# civilian micro-sensors maintained under the 智慧城鄉空品微型感測器 program.
CIVIL_IOT_STA_URL  = "https://sta.colife.org.tw/STA_AirQuality_EPAIoT/v1.0/Datastreams"

# Per-city radius (km) for matching civilian sensors. Outlying islands have
# fewer LASS sensors, so we widen the match radius for them.
_OFFSHORE_REGIONS = {"離島", "東部"}


def _haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorised haversine distance from one point to many (km)."""
    r_lat1 = math.radians(lat1); r_lon1 = math.radians(lon1)
    r_lat2 = np.radians(lat2);   r_lon2 = np.radians(lon2)
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(r_lat1) * np.cos(r_lat2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _fetch_civil_iot_one_city(city_id: str, top: int = 200) -> list[dict]:
    """Pull civilian PM2.5 sensors for ONE city from 民生公共物聯網 SensorThings.

    Critical detail: CivilIoT stores city names in the legacy traditional
    form (e.g. 臺北市, 臺中市, 臺南市, 臺東縣), while our internal `CITIES`
    list uses the everyday form (台北市, 台中市, ...). We build the OData
    $filter with **every alias** that maps to this `city_id` in
    `COUNTY_TO_CITY_ID`, so the 臺/台 variant doesn't drop entire cities.

    The API's default @iot.id ordering biases globally toward early
    sensor deployments (Taoyuan / Yunlin pilot zones), so a global query
    truncated at any reasonable N misses most of Taiwan. Per-city queries
    with the alias-OR filter guarantee representative coverage everywhere.
    """
    aliases = [k for k, v in COUNTY_TO_CITY_ID.items() if v == city_id]
    if not aliases:
        return []
    city_filter = " or ".join(f"Thing/properties/city eq '{a}'" for a in aliases)
    filter_q = f"name eq 'PM2.5' and ({city_filter})"
    try:
        r = requests.get(
            CIVIL_IOT_STA_URL,
            params={
                "$filter": filter_q,
                "$expand": "Observations($orderby=phenomenonTime desc;$top=1),Thing($expand=Locations)",
                "$top":    top,
            },
            timeout=20,
        )
        r.raise_for_status()
        body = r.json()
    except Exception:
        return []
    rows: list[dict] = []
    for ds in body.get("value") or []:
        obs = ds.get("Observations") or []
        if not obs:
            continue
        pm25 = obs[0].get("result")
        thing = ds.get("Thing") or {}
        locs  = thing.get("Locations") or []
        coords = (locs[0].get("location") or {}).get("coordinates") if locs else None
        if not coords or len(coords) < 2:
            continue
        # SensorThings uses GeoJSON ordering: [lon, lat]
        lon, lat = coords[0], coords[1]
        site = (thing.get("properties") or {}).get("stationID") or thing.get("name") or ""
        rows.append({"site": site, "pm25": pm25, "lat": lat, "lon": lon})
    return rows


def _fetch_civil_iot_raw() -> tuple[list[dict] | None, str]:
    """Pull civilian PM2.5 readings from 民生公共物聯網 SensorThings API,
    one HTTP request per city, in parallel.

    Returns (list of dicts with site/pm25/lat/lon, status_msg). The
    SensorThings endpoint exposes ~10,000+ 智慧城鄉空品微型感測器
    (Smart City micro-sensors); we cap per-city at 120 sensors which is
    plenty for a median-aggregation per district.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    rows: list[dict] = []
    failed_cities: list[str] = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_fetch_civil_iot_one_city, city["id"]): city["name"]
                for city in CITIES
            }
            for fut in as_completed(futures, timeout=40):
                city_name = futures[fut]
                try:
                    rows.extend(fut.result())
                except Exception:
                    failed_cities.append(city_name)
    except Exception as e:
        if not rows:
            return None, f"CivilIoT API 失敗：{type(e).__name__}: {str(e)[:80]}"

    if not rows:
        return None, "CivilIoT 全部 20 城市查詢無回應"

    suffix = f"（{len(failed_cities)} 個城市查詢失敗）" if failed_cities else ""
    return rows, f"CivilIoT 取得 {len(rows)} 筆原始紀錄{suffix}"


def _fetch_lass_raw() -> tuple[list[dict] | None, str]:
    """Fallback civilian PM2.5 source - LASS-net community Airbox portal.
    Returns same shape as `_fetch_civil_iot_raw`."""
    try:
        r = requests.get(LASS_AIRBOX_URL, timeout=15)
        r.raise_for_status()
        feeds = (r.json() or {}).get("feeds", []) or []
    except Exception as e:
        return None, f"LASS API 失敗：{type(e).__name__}: {str(e)[:80]}"
    rows: list[dict] = []
    for entry in feeds:
        if not isinstance(entry, dict):
            continue
        ab = entry.get("AirBox") if isinstance(entry.get("AirBox"), dict) else entry
        rows.append({
            "site": ab.get("SiteName") or ab.get("device_id") or ab.get("name") or "",
            "pm25": ab.get("s_d0"),
            "lat":  ab.get("gps_lat") or ab.get("lat"),
            "lon":  ab.get("gps_lon") or ab.get("lon"),
        })
    return rows, f"LASS 取得 {len(rows)} 筆原始紀錄"


def fetch_citizen_sensors() -> tuple[pd.DataFrame | None, "CleaningReport | None", str]:
    """Fetch civilian PM2.5 sensors and aggregate per city.

    Pulls from TWO complementary sources in parallel and merges:
      1. 民生公共物聯網 SensorThings API (sta.colife.org.tw · STA_AirQuality_EPAIoT)
         — official government-curated 智慧城鄉空品微型感測器 network
         (~10,000 sensors; strong on industrial / urban / agricultural belts)
      2. LASS-net Airbox community portal (pm25.lass-net.org)
         — community / academic Airbox sensors (~500 currently online;
         strong on outlying islands 澎湖/金門/馬祖 where the official
         programme has no deployment)

    Both are honest "民生公共物聯網成員" data sources: LASS sensors feed
    into the 民生公共物聯網 platform via SensorThings as well, but the
    community portal exposes a simpler all-in-one snapshot endpoint.

    The returned status_message names both sources and their record
    counts. CleaningReport fields are real (computed from live data, not
    random).

    Cleaning steps:
      1. Drop rows where PM2.5 is missing or out of plausible range (0-500 μg/m³).
      2. Drop rows whose lat/lon fall outside the Taiwan bounding box.
      3. De-duplicate by site/device id (keep first).
      4. For each of our 20 cities, take the median PM2.5 of sensors within
         a radius (5 km inland, 20 km offshore / eastern).
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        ft_civil = pool.submit(_fetch_civil_iot_raw)
        ft_lass  = pool.submit(_fetch_lass_raw)
        civil_rows, civil_status = ft_civil.result()
        lass_rows,  lass_status  = ft_lass.result()

    civil_rows = civil_rows or []
    lass_rows  = lass_rows or []
    rows = civil_rows + lass_rows
    if not rows:
        return None, None, f"{civil_status} ｜ {lass_status}"

    parts = []
    if civil_rows:
        parts.append(f"民生公共物聯網 {len(civil_rows)} 筆")
    if lass_rows:
        parts.append(f"LASS-net {len(lass_rows)} 筆")
    source_label = " + ".join(parts) if parts else "未知來源"

    df = pd.DataFrame(rows)
    raw_count = len(df)

    # 1. PM2.5 in plausible range
    df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
    bad_pm = df["pm25"].isna() | (df["pm25"] <= 0) | (df["pm25"] >= 500)
    df = df[~bad_pm].copy()
    dropped_pm = int(bad_pm.sum())

    # 2. lat/lon in Taiwan bounding box (119-123 E, 21-26.5 N — covers offshore islands)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    in_taiwan = df["lat"].between(21.0, 26.5) & df["lon"].between(119.0, 123.0)
    pre_geo = len(df)
    df = df[in_taiwan].copy()
    dropped_geo = pre_geo - len(df)

    # 3. de-dup by site/device id
    pre_dup = len(df)
    df = df.drop_duplicates(subset=["site"], keep="first")
    dropped_dup = pre_dup - len(df)

    if df.empty:
        return None, CleaningReport(
            raw_records=raw_count, kept_records=0, dropped_records=raw_count,
            drop_reasons={"PM2.5 異常": dropped_pm, "地理範圍外": dropped_geo, "重複": dropped_dup},
        ), f"{source_label}: 清洗後無有效資料"

    # 4. aggregate per city
    sensor_lat = df["lat"].to_numpy()
    sensor_lon = df["lon"].to_numpy()
    sensor_pm  = df["pm25"].to_numpy()

    per_city = []
    for city in CITIES:
        radius_km = 20.0 if city["region"] in _OFFSHORE_REGIONS else 5.0
        d = _haversine_km(city["lat"], city["lon"], sensor_lat, sensor_lon)
        mask = d <= radius_km
        if mask.any():
            per_city.append({
                "city_id":       city["id"],
                "city":          city["name"],
                "citizen_PM2.5": round(float(np.median(sensor_pm[mask])), 1),
                "sensor_count":  int(mask.sum()),
            })
        else:
            per_city.append({
                "city_id":       city["id"],
                "city":          city["name"],
                "citizen_PM2.5": float("nan"),
                "sensor_count":  0,
            })

    cleaning = CleaningReport(
        raw_records=raw_count,
        kept_records=len(df),
        dropped_records=raw_count - len(df),
        drop_reasons={
            "PM2.5 異常": dropped_pm,
            "地理範圍外": dropped_geo,
            "重複":      dropped_dup,
        },
    )
    return pd.DataFrame(per_city), cleaning, f"{source_label}: 取得 {len(df)} 個有效感測器"


# Backward-compat alias — existing callers (app.py) use the old name.
# Delete this once those callers migrate.
fetch_lass_airbox = fetch_citizen_sensors



def fetch_epa_historical(api_key: str | None, hours_back: int = 24) -> pd.DataFrame | None:
    """Pull EPA aqx_p_488 (hourly history). Returns a long-format DataFrame
    with columns: timestamp, city_id, aqi, PM2.5, PM10, O3, NO2, SO2, CO.
    None on failure.

    We grab 2 pages (limit=1000, offset=0/1000) sorted by datacreationdate desc
    to cover ~24 h × 77 stations ≈ 1800 records.
    """
    if not api_key or not api_key.strip():
        return None
    records: list[dict] = []
    try:
        for offset in (0, 1000):
            params = {
                "api_key": api_key.strip(),
                "limit":   1000,
                "offset":  offset,
                "sort":    "datacreationdate desc",
                "format":  "JSON",
            }
            r = requests.get(EPA_HIST_URL, params=params, timeout=20)
            r.raise_for_status()
            body = r.json()
            page = (body.get("records") if isinstance(body, dict) else None) or []
            if not page:
                break
            records.extend(page)
    except Exception:
        return None
    if not records:
        return None

    raw = pd.DataFrame(records)
    cols = {
        "county": _resolve_col(raw, "county", "County", "縣市"),
        "ts":     _resolve_col(raw, "datacreationdate", "DataCreationDate", "publishtime", "PublishTime"),
        "aqi":    _resolve_col(raw, "aqi", "AQI"),
        "pm25":   _resolve_col(raw, "pm2.5", "PM2.5", "pm25"),
        "pm10":   _resolve_col(raw, "pm10", "PM10"),
        "o3":     _resolve_col(raw, "o3", "O3"),
        "no2":    _resolve_col(raw, "no2", "NO2"),
        "so2":    _resolve_col(raw, "so2", "SO2"),
        "co":     _resolve_col(raw, "co", "CO"),
    }
    if cols["county"] is None or cols["ts"] is None or cols["aqi"] is None:
        return None

    raw["_ts"] = pd.to_datetime(raw[cols["ts"]], errors="coerce")
    raw = raw.dropna(subset=["_ts"])
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=hours_back + 1)
    raw = raw[raw["_ts"] >= cutoff]

    rows: list[dict] = []
    for county, sdf in raw.groupby(cols["county"]):
        city_id = COUNTY_TO_CITY_ID.get(str(county))
        if not city_id:
            continue
        for ts, hdf in sdf.groupby(sdf["_ts"].dt.floor("h")):
            def m(key):
                c = cols.get(key)
                if c is None: return None
                v = pd.to_numeric(hdf[c], errors="coerce").dropna()
                return float(v.mean()) if len(v) else None
            aqi = m("aqi")
            if aqi is None or aqi <= 0:
                continue
            rows.append({
                "timestamp": ts.to_pydatetime(),
                "city_id":   city_id,
                "city":      CITY_BY_ID[city_id]["name"],
                "region":    CITY_BY_ID[city_id]["region"],
                "aqi":       round(aqi, 1),
                "PM2.5":     round(m("pm25") or 0, 1),
                "PM10":      round(m("pm10") or 0, 1),
                "O3":        round(m("o3") or 0, 1),
                "NO2":       round(m("no2") or 0, 1),
                "SO2":       round(m("so2") or 0, 2),
                "CO":        round(m("co") or 0, 2),
                "risk":      0.0,
            })
    return pd.DataFrame(rows) if rows else None


def fetch_open_meteo_aq_batch(
    cities: list[dict],
    past_days: int = 1,
    forecast_days: int = 1,
) -> pd.DataFrame | None:
    """Fetch hourly air quality from Open-Meteo (Copernicus CAMS model)
    for many cities in a single request. Returns a long-format DataFrame
    with columns: timestamp, city_id, aqi, PM2.5, PM10, O3, NO2, SO2, CO,
    is_forecast (bool), source='cams'. Free, no key required."""
    if not cities:
        return None
    lats = ",".join(f"{c['lat']:.4f}" for c in cities)
    lons = ",".join(f"{c['lon']:.4f}" for c in cities)
    try:
        r = requests.get(
            OPEN_METEO_AQ_URL,
            params={
                "latitude":      lats,
                "longitude":     lons,
                "hourly":        "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
                "past_days":     past_days,
                "forecast_days": forecast_days,
                "timezone":      "Asia/Taipei",
            },
            timeout=20,
        )
        r.raise_for_status()
        body = r.json()
    except Exception:
        return None

    # Single-location response is a dict; batch is a list. Normalize.
    locations = body if isinstance(body, list) else [body]
    if len(locations) != len(cities):
        # Mismatch — fall back to whatever we got, paired by index
        cities = cities[:len(locations)]
    now_naive = datetime.now()
    rows: list[dict] = []
    for city, loc in zip(cities, locations):
        h = (loc.get("hourly") or {})
        times    = h.get("time") or []
        pm25_arr = h.get("pm2_5") or []
        pm10_arr = h.get("pm10") or []
        o3_arr   = h.get("ozone") or []
        no2_arr  = h.get("nitrogen_dioxide") or []
        so2_arr  = h.get("sulphur_dioxide") or []
        co_arr   = h.get("carbon_monoxide") or []
        aqi_arr  = h.get("us_aqi") or []
        for i, t in enumerate(times):
            try:
                ts = datetime.fromisoformat(t)
            except (ValueError, TypeError):
                continue
            def at(arr, i):
                try:
                    v = arr[i]
                    return float(v) if v is not None else None
                except (IndexError, TypeError, ValueError):
                    return None
            aqi = at(aqi_arr, i)
            pm25 = at(pm25_arr, i)
            if aqi is None and pm25 is None:
                continue
            # Quick risk score using the same weighted blend that EPA-real
            # snapshots use (PM2.5 dominates). Keeps the column shape in
            # parity with EPA history so downstream code (e.g. the time
            # scrubber merge in app.py) doesn't break when CAMS is the
            # ts_df source.
            pm25_v = pm25 or 0.0
            pm10_v = at(pm10_arr, i) or 0.0
            o3_v   = at(o3_arr, i)   or 0.0
            no2_v  = at(no2_arr, i)  or 0.0
            so2_v  = at(so2_arr, i)  or 0.0
            co_v   = (at(co_arr, i) or 0.0) / 1000
            aqi_v  = aqi or 0.0
            _risk = (
                0.40 * (pm25_v / 35) + 0.20 * (aqi_v / 150)
                + 0.15 * (o3_v / 100) + 0.10 * (no2_v / 80)
                + 0.08 * (so2_v / 30) + 0.07 * (co_v / 5)
            )
            _risk = min(100.0, max(0.0, _risk * 100))
            rows.append({
                "timestamp":   ts,
                "city_id":     city["id"],
                "city":        city["name"],
                "region":      city["region"],
                "aqi":         round(aqi, 1) if aqi is not None else None,
                "PM2.5":       round(pm25, 1) if pm25 is not None else None,
                "PM10":        round(pm10_v, 1),
                "O3":          round(o3_v, 1),
                "NO2":         round(no2_v, 1),
                "SO2":         round(so2_v, 2),
                "CO":          round(co_v, 2),
                "risk":        round(_risk, 1),
                "is_forecast": ts > now_naive,
                "source":      "cams",
            })
    return pd.DataFrame(rows) if rows else None


def send_discord_webhook(
    url: str,
    snapshot: pd.DataFrame,
    critic_score: float | None,
    data_mode: str = "real",
) -> tuple[bool, str]:
    """POST a Pipeline-summary embed to a Discord channel webhook.
    Returns (success, message). No-op (returns False, reason) if url is blank."""
    url = (url or "").strip()
    if not url:
        return False, "未填 Discord webhook URL"
    if snapshot is None or snapshot.empty:
        return False, "Snapshot 為空"

    try:
        avg   = float(snapshot["aqi"].mean())
        worst = snapshot.sort_values("aqi", ascending=False).iloc[0]
        best  = snapshot.sort_values("aqi").iloc[0]
    except Exception as e:
        return False, f"Snapshot parse: {type(e).__name__}"

    mode_tag = "LIVE" if data_mode == "real" else "MOCK"
    score_str = f"{critic_score:.1f}/100" if isinstance(critic_score, (int, float)) else "—"
    embed = {
        "title": "🦞 LobsterAQI Pipeline 摘要",
        "description": f"資料來源：{mode_tag} · 覆蓋 {len(snapshot)} 城市",
        "color": 0x00d9ff,
        "fields": [
            {"name": "全國平均 AQI", "value": f"**{avg:.1f}**",
             "inline": True},
            {"name": "最高城市", "value": f"{worst['city']} ({worst['aqi']:.0f})",
             "inline": True},
            {"name": "最低城市", "value": f"{best['city']} ({best['aqi']:.0f})",
             "inline": True},
            {"name": "Critic 評分", "value": score_str, "inline": True},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "LobsterAQI · Taiwan Multi-Agent Air Quality Platform"},
    }
    try:
        r = requests.post(url, json={"embeds": [embed]}, timeout=8)
        ok = r.status_code in (200, 204)
        return ok, f"HTTP {r.status_code}" + ("" if ok else f" · {r.text[:120]}")
    except requests.exceptions.Timeout:
        return False, "Webhook 逾時"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:80]}"


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
    # Google Gemini exposes an OpenAI-compatible endpoint at
    # /v1beta/openai/chat/completions — same request shape as everything
    # below, so it slots right into the generic OpenAI-format branch.
    # Get an API key at https://aistudio.google.com/apikey (free tier).
    "gemini": {
        "name":          "Google Gemini",
        "placeholder":   "AIza...",
        "default_model": "gemini-2.5-flash",
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    # MiniMax (international, where M1 / M2 / abab models live). Sign up at
    # platform.minimaxi.chat; the China platform (api.minimax.chat) is a
    # separate account system and we don't ship that switch here anymore.
    "minimax": {
        "name":          "MiniMax (國際版)",
        "placeholder":   "eyJ...",
        "default_model": "MiniMax-M2.7",
        "base_url":      "https://api.minimaxi.chat/v1",
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
    system: str = "你是台灣空氣品質監測專家，根據 AQI 數據提供準確、有依據的健康建議。回覆請使用繁體中文。",
    # Default cap is generous (~4k output tokens). Callers can pass a higher
    # number for long-form responses; we deliberately don't enforce shorter
    # replies by default — users repeatedly asked for unbounded LLM output.
    max_tokens: int = 4096,
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

    # HTTP statuses commonly transient — worth one quick retry. Gemini in
    # particular returns 503 UNAVAILABLE during peak demand.
    _RETRYABLE = {429, 500, 502, 503, 504}

    def _short_err_message(text: str) -> str:
        """Pull a human-readable message out of a JSON error body."""
        try:
            body = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text[:180]
        if isinstance(body, list) and body:
            body = body[0]
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                msg = err.get("message") or err.get("status") or ""
                if msg:
                    return str(msg)[:180]
        return text[:180]

    try:
        if provider == "anthropic":
            r = None
            for attempt in (1, 2):
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
                if r.status_code in _RETRYABLE and attempt == 1:
                    time.sleep(1.5)
                    continue
                break
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"Anthropic HTTP {r.status_code} · {_short_err_message(r.text)}"
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
            r = None
            for attempt in (1, 2):
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
                if r.status_code in _RETRYABLE and attempt == 1:
                    time.sleep(1.5)
                    continue
                break
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"{provider} HTTP {r.status_code} · {_short_err_message(r.text)}"
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
